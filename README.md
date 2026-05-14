# cool_parser

CoolMessenger `.udb` 메시지 DB를 읽어, 메시지를 검색하고 대화 형태로 확인하기 위한 로컬 뷰어입니다.

현재 단계의 목표는 원본 DB를 직접 수정하지 않고 메시지를 안전하게 확인하는 것입니다. 이후에는 작업용 `.udb` 사본을 대상으로 메시지 수정, 삭제, 추가 가능성을 검토할 예정입니다.

## 주요 기능

- CoolMessenger `.udb` 파일 파싱
- 손상된 SQLite DB에서 `MessageKey` 단위 복구 시도
- 받은 메시지와 보낸 메시지 통합 조회
- 로컬 웹 뷰어 제공
- 키워드 AND 검색
- 연도, 월, 기간 필터
- 받은/보낸 메시지 시각 구분
- 안 읽은 메시지 표시
- 답장/인용 구조를 대화 형태로 표시
- 첨부파일명 표시 및 클릭 복사
- 구성원 번호를 가능한 경우 이름으로 변환

## 실행 방법

Python 3가 필요합니다. 별도 패키지 설치 없이 표준 라이브러리만 사용합니다.

기본 실행:

```powershell
python scripts\run.py
```

기본 실행은 다음 순서로 동작합니다.

1. `%LOCALAPPDATA%\CoolMessenger\Memo.` 폴더에서 `*.udb` 파일을 찾습니다.
2. `.udb`가 하나면 자동 선택하고, 여러 개면 번호로 선택합니다.
3. 선택한 `.udb`를 임시 폴더로 복사합니다.
4. 임시 복사본을 읽기 전용으로 파싱합니다.
5. 로컬 웹 뷰어를 실행합니다.
6. 뷰어 종료 후 임시 파일과 임시 작업 폴더를 정리합니다.

파싱 결과를 남기고 싶으면:

```powershell
python scripts\run.py --keep-work-dir
```

이미 만들어진 SQLite 결과를 열려면:

```powershell
python scripts\run.py --use-existing --db outputs\some_run\merged_messages.sqlite
```

작업 폴더에 둔 `.udb` 사본을 읽으려면:

```powershell
python scripts\run.py --backup --input-dir input
```

## 출력 파일

파싱 과정에서 다음 파일이 만들어질 수 있습니다.

- `merged_messages.sqlite`: 뷰어가 실제로 읽는 통합 DB
- `messages.csv`: 검산이나 외부 도구용 메시지 CSV
- `failed_message_keys.csv`: 손상 등으로 읽지 못한 메시지 키 목록
- `duplicate_candidates.csv`: 중복 후보 목록

CSV는 뷰어의 필수 중간 파일이 아닙니다. 뷰어는 SQLite를 직접 읽습니다.

## 안전 주의

- 실제 메시지 DB에는 개인정보와 민감한 업무 내용이 포함될 수 있습니다.
- `.udb`, `.sqlite`, `outputs`, `input`, `sources`는 Git에 올리지 않도록 `.gitignore`에 포함되어 있습니다.
- 기본 뷰어는 원본 `.udb`를 수정하지 않습니다.
- 라이브 DB는 직접 파싱하지 않고 임시 복사본을 만들어 읽습니다.
- 향후 `.udb` 편집 기능은 반드시 사본을 대상으로만 실험해야 합니다.

## 현재 한계

- 첨부파일을 다운로드하거나 복구하지 않습니다. 파일명만 표시합니다.
- 대화 묶기는 DB 내부 링크가 아니라 본문 안의 인용 표식을 이용한 추정입니다.
- 자연어 검색은 아직 구현되지 않았습니다.
- `.udb` 수정, 삭제, 추가 기능은 아직 실험 전입니다.

## 개발 메모

상세한 진행 상황과 다음 작업은 [plan.md](plan.md)를 참고하세요.
