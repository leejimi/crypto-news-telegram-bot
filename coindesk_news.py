import feedparser

rss_url = "https://news.bitcoin.com/feed/"
feed = feedparser.parse(rss_url)

if feed.bozo:
    print("RSS 파싱 중 오류 발생:", feed.bozo_exception)
else:
    print("RSS 파싱 성공")

print("📰 최신 코인데스크 뉴스")
print("총 뉴스 개수:", len(feed.entries))

for entry in feed.entries[:5]:
    print("\n📌 제목:", entry.title)
    print("🔗 링크:", entry.link)