import hashlib
import json
import re
import urllib.parse
from datetime import datetime
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

# 단순 의전행사, 행정뉴스, 결과 보고, 채용 등 차단 키워드
EXCLUDE_KEYWORDS = [
    "채용", "직원", "합격", "모집", "입찰", "공사", "무대점검", "휴관", "대관신청", "정기점검", "공고문",
    "성료", "성황리", "마쳤다", "폐막", "개최했다", "열렸다", "열린", "끝나", "돌아봤다", "돌아보며",
    "개관식", "준공식", "기념식", "현판식", "개소식", "시무식", "종무식", "업무협약", "mou", "간담회",
    "선포식", "출범식", "기탁", "표창", "수상"
]

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def generate_item_id(title, date_str):
    """카드의 고유 ID 생성 (신규 여부 판별용)"""
    key = f"{clean_text(title)}_{date_str}"
    return hashlib.md5(key.encode('utf-8')).hexdigest()[:10]

def parse_date_range(text):
    """YYYY-MM-DD 또는 M월 D일 추출"""
    matches = re.findall(r'(\d{4})[-.](\d{1,2})[-.](\d{1,2})', text)
    if matches:
        dates = [f"{m[0]}-{int(m[1]):02d}-{int(m[2]):02d}" for m in matches]
        start = dates[0]
        end = dates[1] if len(dates) > 1 else start
        return start, end
    
    current_year = datetime.today().year
    month_day_matches = re.findall(r'(\d{1,2})월\s*(\d{1,2})일', text)
    if month_day_matches:
        dates = [f"{current_year}-{int(m[0]):02d}-{int(m[2]):02d}" for m in month_day_matches]
        start = dates[0]
        end = dates[1] if len(dates) > 1 else start
        return start, end

    return None, None

def is_valid_title(title):
    if len(title) < 5:
        return False
    lower_t = title.lower()
    for bad in EXCLUDE_KEYWORDS:
        if bad in lower_t:
            return False
    return True

def is_too_old(date_str, max_past_days=14):
    if not date_str:
        return False
    try:
        event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.today().date()
        if (today - event_date).days > max_past_days:
            return True
    except Exception:
        pass
    return False

def fetch_google_search_events(query, region_name):
    """공연/콘서트/예술행사에 한정된 구글 뉴스 크롤링"""
    events = []
    today = datetime.today().date()
    
    try:
        # '개관식', '기념식'을 제외하고 순수 공연만 검색 질의
        encoded_q = urllib.parse.quote(f"{query} (공연 OR 콘서트 OR 연극 OR 뮤지컬 OR 페스티벌) -개관식 -준공식 -기념식")
        rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(rss_url, headers=HEADERS, timeout=8)
        
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:8]:
                raw_title = clean_text(item.find("title").text if item.find("title") is not None else "")
                link = item.find("link").text if item.find("link") is not None else ""
                pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""
                
                title = re.sub(r'\s*-\s*[^ -]+$', '', raw_title)
                
                if not is_valid_title(title):
                    continue
                
                if pub_date_str:
                    try:
                        pub_dt = parsedate_to_datetime(pub_date_str).date()
                        if (today - pub_dt).days > 30:
                            continue
                    except Exception:
                        pass

                start_date, end_date = parse_date_range(title)
                if start_date:
                    if is_too_old(end_date or start_date):
                        continue
                else:
                    start_date = datetime.today().strftime('%Y-%m-%d')
                    end_date = start_date

                events.append({
                    "id": generate_item_id(title, start_date),
                    "title": title,
                    "venue": f"{region_name} 문화예술공간",
                    "region": region_name,
                    "genre": "공연/축제",
                    "startDate": start_date,
                    "endDate": end_date,
                    "price": "보도/예매 확인",
                    "link": link,
                    "source": "언론/문화소식"
                })
    except Exception as e:
        print(f"[구글 피드 오류 - {region_name}]: {e}")
        
    return events

def fetch_jincheon_art():
    """진천예술의전당 공식 일정 스크래핑"""
    events = []
    base_url = "https://jinculture.or.kr"
    try:
        res = requests.get(f"{base_url}/sub.php?code=9", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.find_all(string=re.compile(r'기획공연|대관공연|전시|콘서트'))
        
        for s in items:
            p = s.find_parent(["div", "li", "tr"])
            if not p: continue
            text = clean_text(p.get_text(" "))
            
            start_date, end_date = parse_date_range(text)
            if not start_date or is_too_old(end_date or start_date):
                continue

            title_m = re.search(r'(<[^>]+>|\[[^\]]+\]|기획공연\s*([^\s]+.*)|대관공연\s*([^\s]+.*))', text)
            title = title_m.group(0) if title_m else text[:35]
            title = re.sub(r'자세히보기|날짜.*|장소.*|금액.*', '', title).strip()
            
            if not is_valid_title(title):
                continue

            link_elem = p.find("a", href=True)
            href = link_elem["href"] if link_elem else "sub.php?code=9"
            link = f"{base_url}/{href.lstrip('/')}" if not href.startswith("http") else href

            events.append({
                "id": generate_item_id(title, start_date),
                "title": title,
                "venue": "진천예술의전당 진아트홀",
                "region": "진천군",
                "genre": "기획/대관",
                "startDate": start_date,
                "endDate": end_date,
                "price": "상세 확인",
                "link": link,
                "source": "생거진천문화재단"
            })
    except Exception as e:
        print(f"[진천 오류]: {e}")
    return events

def fetch_eumseong_art():
    """음성문화예술회관 공식 일정 스크래핑"""
    events = []
    base_url = "https://www.esart.go.kr"
    try:
        res = requests.get(base_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        lines = [clean_text(l) for l in soup.get_text("\n").split("\n") if clean_text(l)]
        
        for i, line in enumerate(lines):
            if any(k in line for k in ["콘서트", "앙상블", "뮤지컬", "페스티벌", "공연", "갈라"]):
                if not is_valid_title(line):
                    continue
                context = " ".join(lines[max(0, i-2):min(len(lines), i+3)])
                start_date, end_date = parse_date_range(context)
                
                if start_date and not is_too_old(end_date or start_date):
                    title = re.sub(r'^(공연|행사)\s*', '', line).strip()
                    if is_valid_title(title):
                        events.append({
                            "id": generate_item_id(title, start_date),
                            "title": title,
                            "venue": "음성문화예술회관",
                            "region": "음성군",
                            "genre": "기획공연",
                            "startDate": start_date,
                            "endDate": end_date,
                            "price": "홈페이지 예매",
                            "link": base_url,
                            "source": "음성문화예술회관"
                        })
    except Exception as e:
        print(f"[음성 오류]: {e}")
    return events

def clean_and_deduplicate(events):
    """뉴스 기사 중복 및 개관 관련 중복 집중 필터링"""
    filtered = []
    seen_sets = []

    for item in events:
        title = item["title"]
        # 한글/영문 단어만 추출하여 단어 세트 생성
        words = set(re.findall(r'[가-힣a-zA-Z0-9]{2,}', title))
        
        # '개관' 관련 단어가 들어간 일반 기사는 중복 검사 강화
        is_opening = any(w in title for w in ["개관", "새단장", "오픈"])
        
        is_duplicate = False
        for seen in seen_sets:
            # 두 기사 제목 간 겹치는 단어가 3개 이상이거나, 개관 관련 단어가 2개 이상 겹치면 중복 판정
            common = words.intersection(seen)
            if len(common) >= 3 or (is_opening and len(common) >= 2):
                is_duplicate = True
                break
                
        if not is_duplicate:
            seen_sets.append(words)
            filtered.append(item)
            
    return filtered

def main():
    print("통합 문화공연 스마트 크롤러 시작...")
    all_events = []

    all_events.extend(fetch_jincheon_art())
    all_events.extend(fetch_eumseong_art())
    all_events.extend(fetch_google_search_events("진천 문화재단", "진천군"))
    all_events.extend(fetch_google_search_events("충북혁신도시 음성", "음성군"))
    all_events.extend(fetch_google_search_events("천안예술의전당 공연", "천안시"))
    all_events.extend(fetch_google_search_events("안성맞춤아트홀 공연", "안성시"))

    # 중복 제거 및 날짜 정렬
    cleaned_events = clean_and_deduplicate(all_events)
    cleaned_events.sort(key=lambda x: x.get("startDate", "9999-12-31"))

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(cleaned_events, f, ensure_ascii=False, indent=2)

    print(f"필터링 완료: 총 {len(cleaned_events)}건 저장 (data.json)")

if __name__ == "__main__":
    main()
