from dotenv import load_dotenv
load_dotenv()  # .env 파일에서 환경 변수를 로드합니다.

import os, json, hashlib, feedparser, requests, openai, schedule, time, textwrap

# --- 설정 변수 ---
RSS_URL = "https://news.bitcoin.com/feed/"
KEYWORDS = ["bitcoin", "ethereum", "defi", "etf", "sec"]
HISTORY_FILE = "sent_news.json"

# --- 환경 변수 로드 ---
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 텔레그램 API URL 구성
if not TG_BOT_TOKEN:
    print("ERROR: TG_BOT_TOKEN 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
    exit(1) # 토큰 없으면 스크립트 종료
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"

# OpenAI 클라이언트 초기화
if not OPENAI_API_KEY:
    print("ERROR: OPENAI_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
    exit(1) # API 키 없으면 스크립트 종료
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# --- 유틸리티 함수 ---

def load_history():
    """이전에 전송된 뉴스의 해시를 불러옵니다."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except json.JSONDecodeError:
            print(f"WARNING: {HISTORY_FILE} 파일이 손상되었거나 비어있습니다. 새로 시작합니다.")
            return set()
    return set()

def save_history(history):
    """전송된 뉴스의 해시를 저장합니다."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(list(history), f, indent=4)
    except IOError as e:
        print(f"ERROR: {HISTORY_FILE} 파일 저장 중 오류 발생: {e}")

def item_hash(entry):
    """뉴스 항목의 고유 해시를 생성합니다."""
    raw = entry.link or entry.id or entry.title
    if not raw: # 링크, ID, 제목 모두 없으면 해시 생성 불가
        return None
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def send_telegram(msg):
    """텔레그램으로 메시지를 전송합니다."""
    if not TG_CHAT_ID:
        print("ERROR: TG_CHAT_ID 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return

    data = {"chat_id": TG_CHAT_ID, "text": msg, "disable_web_page_preview": True}
    
    print(f"DEBUG: 텔레그램 API 요청 URL: {TELEGRAM_API_URL}") # 디버깅용
    print(f"DEBUG: 텔레그램 Chat ID: {TG_CHAT_ID}") # 디버깅용
    print(f"DEBUG: 텔레그램 메시지 길이: {len(msg)}") # 디버깅용
    print(f"DEBUG: 텔레그램 메시지 시작 부분: '{msg[:100]}...'") # 디버깅용

    try:
        resp = requests.post(TELEGRAM_API_URL, data=data)
        resp.raise_for_status() # 200번대 응답이 아니면 예외 발생
        print("텔레그램 전송 결과:", resp.status_code, resp.text)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: 텔레그램 전송 중 오류 발생: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"ERROR: 텔레그램 응답 상태 코드: {e.response.status_code}")
            print(f"ERROR: 텔레그램 응답 내용: {e.response.text}")
    except Exception as e:
        print(f"ERROR: 예상치 못한 텔레그램 전송 오류: {e}")

def summarise_ko(title, summary):
    """OpenAI를 사용하여 뉴스를 한국어로 요약합니다."""
    prompt = f"뉴스 제목: {title}\n내용: {summary}\n이 뉴스를 3~4문장으로 간략하게 한글로 요약해줘."
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.7, # 창의성 조절
            max_tokens=200 # 요약 최대 길이 제한
        )
        summary_text = response.choices[0].message.content.strip()
        if not summary_text:
            print(f"WARNING: OpenAI 요약 결과가 비어있습니다. (제목: {title})")
            return "요약 내용을 가져올 수 없습니다."
        return summary_text
    except openai.APIError as e:
        print(f"ERROR: OpenAI API 오류 발생: {e}")
        # API 오류가 발생하면, 해당 뉴스는 요약 없이 보내거나 스킵할 수 있습니다.
        # 여기서는 오류 메시지를 요약으로 반환합니다.
        return f"OpenAI 요약 서비스 오류: {e.code} - {e.message}"
    except Exception as e:
        print(f"ERROR: OpenAI 요약 중 예상치 못한 오류 발생: {e}")
        return "OpenAI 요약 중 알 수 없는 오류 발생."

# --- 주요 로직 함수 ---
def fetch_and_alert():
    """새로운 뉴스를 가져와 필터링하고 텔레그램으로 전송합니다."""
    print("\n🔍 뉴스 확인 시작")
    history = load_history()
    print(f"DEBUG: 현재 히스토리 항목 수: {len(history)}")

    feed = feedparser.parse(RSS_URL)

    if feed.bozo:
        print(f"ERROR: RSS 파싱 오류 발생: {feed.bozo_exception}")
        return

    print(f"DEBUG: RSS 피드에서 {len(feed.entries)}개의 항목을 가져왔습니다.")
    new_history = set(history)
    processed_count = 0
    sent_count = 0

    # 최근 20개 항목만 확인
    for entry in feed.entries[:20]:
        item_h = item_hash(entry)
        if item_h is None:
            print(f"WARNING: 제목, 링크, ID가 없는 항목을 건너뜁니다.")
            continue

        if item_h in history:
            # print(f"DEBUG: 이미 전송된 뉴스: {entry.title}")
            continue # 이미 전송된 뉴스 스킵

        title_lc = entry.title.lower() if entry.title else ""
        
        # 키워드 필터링
        if not any(k in title_lc for k in KEYWORDS):
            # print(f"DEBUG: 키워드 불일치: {entry.title}")
            continue # 키워드 없는 뉴스 스킵
        
        processed_count += 1
        print(f"DEBUG: 처리 중인 뉴스: {entry.title}")

        # 요약
        summary_text = summarise_ko(entry.title, entry.get("summary", ""))
        
        # 메시지 구성
        msg = f"📰 {entry.title}\n\n{summary_text}\n\n🔗 {entry.link}"

        # 메시지가 비어있는지 다시 확인
        if not msg.strip() or len(msg.strip()) < 10: # 최소 10자 미만이면 유효하지 않다고 판단
            print(f"WARNING: 메시지 내용이 너무 짧거나 비어있어 전송을 건너뜁니다. (제목: {entry.title})")
            continue

        send_telegram(msg)
        print("✅ 알림 전송 완료:", entry.title)
        new_history.add(item_h)
        sent_count += 1

    save_history(new_history)
    print(f"DEBUG: 최종 히스토리 항목 수: {len(new_history)}")
    print(f"뉴스 확인 완료. 처리된 새 항목: {processed_count}개, 텔레그램 전송: {sent_count}개")

# --- 스케줄러 설정 및 실행 ---
print("⏰ 10분마다 뉴스 체크 시작!")

# 스크립트 시작 시 한 번 실행
fetch_and_alert()

# 이후 10분마다 반복 실행
schedule.every(10).minutes.do(fetch_and_alert)

while True:
    schedule.run_pending()
    time.sleep(1)