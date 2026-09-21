import json
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def parse_date_range(text):
    """텍스트에서 YYYY-MM-DD 또는 YYYY.MM.DD 형태 날짜 2개까지 추출"""
    matches = re.findall(r'(\d{4})[-.](\d{1,2})[-.](\d{1,2})', text)
    if not matches:
        return None, None
    
    dates = [f"{m[0]}-{int(m[1]):02d}-{int(m[2]):02d}" for m in matches]
    start_date = dates[0]
    end_date = dates[1] if len(dates) > 1 else start_date
    return start_date, end_date

def fetch_jincheon_art():
    """진천예술의전당 (생거진천문화재단) 메인 및 공연 일정 스크래핑"""
    events = []
    base_url = "https://jinculture.or.kr"
    
    try:
        res = requests.get(base_url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 메인 페이지 및 일정 영역 탐색
        sections = soup.find_all(string=re.compile(r'기획공연|대관공연|기획전시|공연'))
        seen_titles = set()

        for s in sections:
            parent = s.find_parent(["div", "li", "tr"])
            if not parent:
                continue
            text = clean_text(parent.get_text(" "))
            
            # 날짜 정규식 매칭
            start_date, end_date = parse_date_range(text)
            if not start_date:
                continue

            # 공연명 추출
            title_match = re.search(r'(<[^>]+>|\[[^\]]+\]|기획공연\s*([^\s]+.*)|대관공연\s*([^\s]+.*))', text)
            title = title_match.group(0) if title_match else text[:30]
            title = re.sub(r'자세히보기|날짜.*|장소.*', '', title).strip()

            if title in seen_titles or len(title) < 2:
                continue
            seen_titles.add(title)

            # 상세 링크 추출
            link_elem = parent.find("a", href=True)
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
                "price": "상세페이지 확인",
                "link": link,
                "source": "생거진천문화재단"
            })
    except Exception as e:
        print(f"[진천예술의전당 파싱 알림]: {e}")

    # 비상시 기본 안내 데이터 보존
    if not events:
        events.append({
            "id": "jc-fallback",
            "title": "진천예술의전당 기획 및 대관 공연 안내",
            "venue": "진천예술의전당",
            "region": "진천군",
            "genre": "공연안내",
            "startDate": datetime.today().strftime('%Y-%m-%d'),
            "endDate": datetime.today().strftime('%Y-%m-%d'),
            "price": "홈페이지 공지 참조",
            "link": "https://jinculture.or.kr/sub.php?code=9",
            "source": "생거진천문화재단"
        })
    return events

def fetch_eumseong_art():
    """음성문화예술회관 메인 일정 파싱"""
    events = []
    base_url = "https://www.esart.go.kr"
    
    try:
        res = requests.get(base_url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 텍스트 내 일정 항목 정규식 탐색
        body_text = soup.get_text("\n")
        lines = [clean_text(line) for line in body_text.split("\n") if clean_text(line)]
        
        for i, line in enumerate(lines):
            # 브런치 콘서트, 기획공연 등 키워드 필터링
            if any(k in line for k in ["공연", "콘서트", "갈라", "앙상블", "뮤지컬", "페스티벌"]):
                if any(ex in line for ex in ["점검", "공사", "체육대회"]):
                    continue
                
                # 주변 3개 라인 내에서 날짜 탐색
                context = " ".join(lines[max(0, i-2):min(len(lines), i+3)])
                start_date, end_date = parse_date_range(context)
                
                if start_date:
                    title = re.sub(r'^(공연|행사|점검)\s*', '', line).strip()
                    if len(title) > 3 and not any(e["title"] == title for e in events):
                        events.append({
                            "id": f"es-{len(events)+1}",
                            "title": title,
                            "venue": "음성문화예술회관 대공연장",
                            "region": "음성군",
                            "genre": "기획/초청공연",
                            "startDate": start_date,
                            "endDate": end_date,
                            "price": "홈페이지 예매",
                            "link": base_url,
                            "source": "음성문화예술회관"
                        })
    except Exception as e:
        print(f"[음성문화예술회관 파싱 알림]: {e}")

    return events

def main():
    print("문화시설 공연 데이터 수집 시작...")
    all_events = []
    
    all_events.extend(fetch_jincheon_art())
    all_events.extend(fetch_eumseong_art())

    # 시작일 기준 오름차순 정렬 (최신순)
    all_events.sort(key=lambda x: x.get("startDate", "9999-12-31"))

    # 중복 제거
    unique_events = []
    seen = set()
    for e in all_events:
        key = (e['title'], e['startDate'])
        if key not in seen:
            seen.add(key)
            unique_events.append(e)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(unique_events, f, ensure_ascii=False, indent=2)
        
    print(f"총 {len(unique_events)}건의 공연 데이터가 data.json에 저장되었습니다.")

if __name__ == "__main__":
    main()
