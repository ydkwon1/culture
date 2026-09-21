import json
import re
import urllib.parse
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

# 1. 채용/점검 및 '이미 종료된 행사' 결과 기사 차단 키워드
EXCLUDE_KEYWORDS = [
    "채용", "직원", "합격", "모집", "입찰", "공사", "무대점검", "휴관", "대관신청", "정기점검", "공고문",
    "성료", "성황리", "마쳤다", "폐막", "개최했다", "열렸다", "열린", "끝나", "돌아봤다", "돌아보며", "기념식 가져"
]

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def normalize_title_key(title):
    """중복 기사 병합을 위한 핵심 키 생성 (특수기호, 기사 수식어 제거)"""
    t = re.sub(r'\[[^\]]*\]|\([^\)]*\)|<[^>]*>|【[^】]*】', '', title)
    t = re.sub(r'(개최|열린다|선봬|진행|추진|선보여|풍성|맞이).*$', '', t)
    t = re.sub(r'[^가-힣a-zA-Z0-9]', '', t)
    return t[:10]  # 앞쪽 핵심 단어 10글자기준 동일 소식 판단

def parse_date_range(text):
    """텍스트에서 YYYY-MM-DD 또는 YYYY.MM.DD 또는 'M월 D일' 날짜 추출"""
    # 1) 2026-09-21 또는 2026.09.21
    matches = re.findall(r'(\d{4})[-.](\d{1,2})[-.](\d{1,2})', text)
    if matches:
        dates = [f"{m[0]}-{int(m[1]):02d}-{int(m[2]):02d}" for m in matches]
        start = dates[0]
        end = dates[1] if len(dates) > 1 else start
        return start, end
    
    # 2) '9월 25일' 형태 매칭 (연도는 올해 연도 자동 부여)
    current_year = datetime.today().year
    month_day_matches = re.findall(r'(\d{1,2})월\s*(\d{1,2})일', text)
    if month_day_matches:
        dates = [f"{current_year}-{int(m[0]):02d}-{int(m[1]):02d}" for m in month_day_matches]
        start = dates[0]
        end = dates[1] if len(dates) > 1 else start
        return start, end

    return None, None

def is_valid_title(title):
    if len(title) < 5:
        return False
    for bad in EXCLUDE_KEYWORDS:
        if bad in title:
            return False
    return True

def is_too_old(date_str, max_past_days=14):
    """오늘 기준 14일 이상 지난 과거 공연은 True 반환 (필터링 대상)"""
    if not date_str:
        return False
    try:
        event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.today().date()
        # 오늘보다 14일 이상 전이면 과거 데이터로 판단하여 버림
        if (today - event_date).days > max_past_days:
            return True
    except Exception:
        pass
    return False

def fetch_google_search_events(query, region_name):
    """Google News RSS 피드 크롤링 및 구식 뉴스/종료된 공연 제거"""
    events = []
    today = datetime.today().date()
    
    try:
        # '예정', '개최' 등 미래/현재 시점 수식어 조합
        encoded_q = urllib.parse.quote(f"{query} 공연 OR 콘서트")
        rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(rss_url, headers=HEADERS, timeout=8)
        
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:8]:
                raw_title = clean_text(item.find("title").text if item.find("title") is not None else "")
                link = item.find("link").text if item.find("link") is not None else ""
                pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""
                
                # 언론사 꼬리표(' - 충청투데이 등') 제거
                title = re.sub(r'\s*-\s*[^ -]+$', '', raw_title)
                
                # 1. 종료/결과/채용 키워드 필터링
                if not is_valid_title(title):
                    continue
                
                # 2. 기사 자체 발행일 필터 (발행된 지 30일 이상 지난 묵은 기사는 스킵)
                if pub_date_str:
                    try:
                        pub_dt = parsedate_to_datetime(pub_date_str).date()
                        if (today - pub_dt).days > 30:
                            continue
                    except Exception:
                        pass

                # 3. 공연 실제 날짜 파싱 및 과거 행사 필터
                start_date, end_date = parse_date_range(title)
                
                if start_date:
                    # 5월 등 이미 몇 달 전 지난 공연 날짜면 즉시 버림
                    if is_too_old(end_date or start_date):
                        continue
                else:
                    # 날짜가 제목에 없으면 최근 기사 발행일을 임시 기준일로 지정
                    start_date = datetime.today().strftime('%Y-%m-%d')
                    end_date = start_date

                events.append({
                    "id": f"goog-{len(events)+1}-{region_name}",
                    "title": title,
                    "venue": f"{region_name} 문화예술공간",
                    "region": region_name,
                    "genre": "공연/축제",
                    "startDate": start_date,
                    "endDate": end_date,
                    "price": "보도/안내 참조",
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
                "id": f"jc-{len(events)+1}",
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
                            "id": f"es-{len(events)+1}",
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

def main():
    print("통합 문화공연 스마트 크롤링 가동...")
    all_events = []

    # 1. 공식 문화재단/예술회관 스크래핑
    all_events.extend(fetch_jincheon_art())
    all_events.extend(fetch_eumseong_art())

    # 2. 구글 뉴스 인근 권역 검색 크롤링
    all_events.extend(fetch_google_search_events("진천예술의전당", "진천군"))
    all_events.extend(fetch_google_search_events("진천 문화 축제", "진천군"))
    all_events.extend(fetch_google_search_events("음성문화예술회관", "음성군"))
    all_events.extend(fetch_google_search_events("천안예술의전당 기획공연", "천안시"))
    all_events.extend(fetch_google_search_events("안성맞춤아트홀 공연", "안성시"))

    # 3. 고도화된 중복 제거 및 클렌징
    unique_events = []
    seen_keys = set()

    for item in all_events:
        # 오래된 과거 공연 재차 검증
        if is_too_old(item.get("endDate") or item.get("startDate")):
            continue
            
        norm_key = normalize_title_key(item["title"])
        # 같은 권역 내에서 핵심 제목이 겹치면 중복으로 보고 하나만 유지
        composite_key = f"{item['region']}_{norm_key}"
        
        if composite_key not in seen_keys:
            seen_keys.add(composite_key)
            unique_events.append(item)

    # 시작일자 기준 오름차순 정렬 (다가오는 공연이 위로 오도록)
    unique_events.sort(key=lambda x: x.get("startDate", "9999-12-31"))

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(unique_events, f, ensure_ascii=False, indent=2)

    print(f"필터링 완료: 총 {len(unique_events)}건의 유효 공연 정보 저장 (data.json)")

if __name__ == "__main__":
    main()
