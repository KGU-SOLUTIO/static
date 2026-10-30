# static

## export.py 사용법

DOMJudge 대회 결과를 Spotboard 정적 스코어보드로 변환하여 출력합니다.

- 실행 환경
  - Python 표준 라이브러리만 사용하므로 별도의 패키지 설치가 필요하지 않습니다.
- 계정 정보 설정 (PowerShell)
  - `$env:DOMJUDGE_USER = 'reader'`
  - `$env:DOMJUDGE_PASS = '비밀번호'`
  - 설정하지 않은 경우 실행 시 입력을 요청합니다.
  - DOMJudge의 users -> add user에서 API reader 역할을 지닌 계정을 생성해 사용하여야 합니다.
- 최초 실행 (Spotboard 웹앱 복사 포함)
  - `python export.py --url https://contest.solutio.page --cid KGUPC-2-Beginner-R --out kgupc/2026/beginner --webapp spotboard-webapp`
- 결과 갱신
  - `python export.py --url https://contest.solutio.page --cid KGUPC-2-Beginner-R --out kgupc/2026/beginner`
  - 웹앱이 이미 복사된 경우 `--webapp` 옵션은 생략할 수 있습니다.
- 옵션
  - `--url`: DOMJudge 서버 주소
  - `--cid`: 콘테스트 ID (`/api/v4/contests` 응답의 `id` 값)
  - `--out`: 출력 폴더 경로
  - `--webapp`: 압축을 해제한 Spotboard 웹앱 폴더 경로 (최초 1회 필요)
- 생성 파일
  - `contest.json`, `runs.json`: 실행할 때마다 새로 생성됩니다.
  - `award_slide.json`: 파일이 없는 경우에만 빈 목록으로 생성되며, 수상 정보는 직접 입력해야 합니다.
- 유의 사항
  - 채점 대기 중인 제출이 있다는 경고가 출력되면 채점 완료 후 다시 실행해야 합니다.
  - DOMJudge의 페널티가 20분이 아닌 경우 Spotboard의 순위와 다를 수 있습니다.
  - 시상식은 실행 결과 마지막에 출력되는 시상식 모드 주소(`?award=true&time=...`)를 통해 진행합니다.
