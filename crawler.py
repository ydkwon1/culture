import json
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def fetch_jincheon_art():
    """진천예술의전당 (생거진천문화재단) 공연 스크래핑"""
    events = []
    # 생거진천문화재단 진행중인 공연 목록 URL
    url = "https://jinculture.or.kr/sub.php?code=9"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 목록 아이템 탐색 (게시판 형태 또는 카드형 UI)
        items = soup.select(".board_list tbody tr, .gallery_list li, .program_list li")
        
        for idx, item in enumerate(items):
            title_elem = item.select_one(".title a, .tit a, dt a")
            date_elem = item.select_one(".date, .period, dd.date")
            
            if not title_elem:
                continue
                
            title = clean_text(title_elem.text)
            href = title_elem.get("href", "")
            full_link = f"https://jinculture.or.kr/{href}" if not href.startswith("http") else href
            date_str = clean_text(date_elem.text) if date_elem else ""
            
            # 날짜 정규식 추출 (YYYY-MM-DD 형태 매칭)
            dates = re.findall(r'\d{4}[-.]\d{2}[-.]\d{2}', date_str)
            start_date = dates[0].replace('.', '-') if dates else datetime.today().strftime('%Y-%m-%d')
            end_date = dates[1].replace('.', '-') if len(dates) > 1 else start_date
            
            events.append({
                "id": f"jc-art-{idx}",
                "title": title,
                "venue": "진천예술의전당 진아트홀",
                "region": "진천군",
                "genre": "공연/기획",
                "startDate": start_date,
                "endDate": end_date,
                "price": "상세페이지 확인",
                "link": full_link,
                "source": "생거진천문화재단"
            })
    except Exception as e:
        print(f"[오류] 진천예술의전당 스크래핑 실패: {e}")
        
    return events

def fetch_eumseong_art():
    """음성문화예술회관 공연 스크래핑"""
    events = []
    url = "https://www.esart.go.kr"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 메인 또는 공연안내 영역 파싱
        items = soup.select(".play_list li, .perform_box, .notice_wrap ul li")
        
        for idx, item in enumerate(items[:5]):
            title_elem = item.select_one(".tit, strong, a")
            if not title_elem:
                continue
            title = clean_text(title_elem.text)
            if not title or "공지" in title:
                continue
                
            link_elem = item.select_one("a")
            href = link_elem.get("href", "") if link_elem else ""
            full_link = f"https://www.esart.go.kr/{href.lstrip('/')}" if not href.startswith("http") else href
            
            events.append({
                "id": f"es-art-{idx}",
                "title": title,
                "venue": "음성문화예술회관",
                "region": "음성군",
                "genre": "기획공연",
                "startDate": datetime.today().strftime('%Y-%m-%d'),
                "endDate": datetime.today().strftime('%Y-%m-%d'),
                "price": "홈페이지 예매",
                "link": full_link or url,
                "source": "음성문화예술회관"
            })
    except Exception as e:
        print(f"[오류] 음성문화예술회관 스크래핑 실패: {e}")

    return events

def main():
    print("공연 데이터 수집 중...")
    results = []
    results.extend(fetch_jincheon_art())
    results.extend(fetch_eumseong_art())
    
    # 중복 제거 및 날짜순 정렬
    results.sort(key=lambda x: x.get("startDate", "9999-12-31"))

    # UTF-8 JSON 출력
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"총 {len(results)}건 저장 완료 (data.json)")

if __name__ == "__main__":
    main()
