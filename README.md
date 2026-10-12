# RESCENE 영상 모아보기

리센느가 언급된 유튜브 영상을 매일 저녁 7시(KST)에 모아 보여주는 개인용 페이지.

## 수집 기준
- 검색어: `#리센느`, `리센느`, `RESCENE` (제목·설명·태그에 리센느/RESCENE 이 있어야 통과)
- **롱폼**: 조회수 5만 이상. 최근 업로드 20개 중 절반 넘게 리센느 영상인 채널은 팬 채널로 보고 제외 (공식 RESCENE·더뮤즈 채널은 예외)
- **쇼츠**: 조회수 10만 이상. 팬 채널 허용
- 쇼츠 판별: `youtube.com/shorts/ID` 가 200 이면 쇼츠, 303 이면 롱폼
- `blocklist.txt` 에 적은 채널은 둘 다에서 제외 (수정 후 커밋하면 바로 반영)

## 구성
| 파일 | 역할 |
|---|---|
| `scripts/update.py` | 유튜브 API 검색 → `data/state.json`(내부 상태), `data/videos.json`(페이지용) 갱신 |
| `.github/workflows/update.yml` | 매일 10:00 UTC 실행 + 커밋 + Pages 배포. 수동 실행은 Actions 탭 → Run workflow |
| `index.html`, `app.js`, `style.css` | 페이지 |

## 설정
저장소 Settings → Secrets and variables → Actions 에 `YOUTUBE_API_KEY` 등록.

## 테스트
```
python3 -m unittest discover -s tests
```
