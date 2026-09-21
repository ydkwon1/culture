import json
import re
import urllib.parse
from datetime import datetime
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

# 채용, 대관공고 등 노이즈 차단 키워드
EXCLUDE_KEYWORDS = ["채용", "직원", "합격", "모집", "입찰", "공사", "무대점검", "휴관", "대관신청", "정기점검", "공고문"]

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def parse_date_range(text):
    matches = re.findall(r'(\d{4})[-.](\d{1,2})[-.](\d{1,2})', text)
    if not matches:
        return None, None
    dates = [f"{m[0]}-{int(m[1]):02d}-{int(m[2]):02d}" for m in matches]
    start = dates[0]
    end = dates[1] if len(dates) > 1 else start
    return start, end

def is_valid_title(title):
    if len(title) < 4:
        return False
    for bad in EXCLUDE_KEYWORDS:
        if bad in title:
            return False
    return True

def fetch_google_search_events(query, region_name):
    """Google News RSS 피드를 통해 지역 문화공연 소식 크롤링"""
    events = []
    try:
        encoded_q = urllib.parse.quote(f"{query} 공연 콘서트")
        rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(rss_url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:5]:
                title = clean_text(item.find("title").text if item.find("title") is not None else "")
                link = item.find("link").text if item.find("link") is not None else ""
                pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                
                # 언론사 태그 분리 및 필터
                title = re.sub(r'\s*-\s*[^ -]+$', '', title)
                if not is_valid_title(title):
                    continue
                
                # 날짜 파싱 시도
                start_date, end_date = parse_date_range(title)
                if not start_date:
                    start_date = datetime.today().strftime('%Y-%m-%d')
                    end_date = start_date

                events.append({
                    "id": f"goog-{len(events)+1}-{region_name}",
                    "title": title,
                    "venue": f"{region_name} 인근 문화공간",
                    "region": region_name,
                    "genre": "문화소식",
                    "startDate": start_date,
                    "endDate": end_date,
                    "price": "보도/예매 확인",
                    "link": link,
                    "source": "구글 문화레이더"
                })
    except Exception as e:
        print(f"[구글 피드 오류 - {region_name}]: {e}")
    return events

def fetch_jincheon_art():
    """진천예술의전당 스크래핑"""
    events = []
    base_url = "https://jinculture.or.kr"
    try:
        res = requests.get(f"{base_url}/sub.php?code=9", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 목록 영역 파싱
        items = soup.find_all(string=re.compile(r'기획공연|대관공연|전시|콘서트'))
        for s in items:
            p = s.find_parent(["div", "li", "tr"])
            if not p: continue
            text = clean_text(p.get_text(" "))
            
            start_date, end_date = parse_date_range(text)
            if not start_date: continue

            # 제목 추출
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
                "genre": "기획/대관공연",
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
    """음성문화예술회관 스크래핑"""
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
                
                title = re.sub(r'^(공연|행사)\s*', '', line).strip()
                if start_date and is_valid_title(title):
                    events.append({
                        "id": f"es-{len(events)+1}",
                        "title": title,
                        "venue": "음성문화예술회관 대공연장",
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
    print("통합 문화공연 크롤링 가동...")
    all_events = []

    # 1. 지자체 예술의전당 직접 스크래핑
    all_events.extend(fetch_jincheon_art())
    all_events.extend(fetch_eumseong_art())

    # 2. 구글 기반 인근 지역(진천, 음성, 천안, 안성) 실시간 검색 크롤링
    all_events.extend(fetch_google_search_events("진천", "진천군"))
    all_events.extend(fetch_google_search_events("충북혁신도시 음성", "음성군"))
    all_events.extend(fetch_google_search_events("천안예술의전당", "천안시"))
    all_events.extend(fetch_google_search_events("안성맞춤아트홀", "안성시"))

    # 중복 제거 (제목 유사성 및 날짜 기준)
    unique_events = []
    seen = set()
    for e in all_events:
        clean_key = re.sub(r'[^가-힣a-zA-Z0-9]', '', e['title'])[:12]
        if clean_key not in seen:
            seen.add(clean_key)
            unique_events.append(e)

    # 날짜 오름차순 정렬
    unique_events.sort(key=lambda x: x.get("startDate", "9999-12-31"))

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(unique_events, f, ensure_ascii=False, indent=2)

    print(f"총 {len(unique_events)}건 수집 완료 (data.json)")

if __name__ == "__main__":
    main()
