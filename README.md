# FileFlow Lite

Windows 파일 탐색기에 안전한 폴더 평탄화와 일괄 순번 이름짓기를 더하는 무료 오픈소스 도구입니다. 로컬 서버나 유료 서비스 없이 장치 안에서 실행됩니다.

## 주요 기능

- 모든 하위 폴더의 파일을 한 폴더로 **복사 또는 이동**
- 이름 충돌 시 **순번 자동 부여** 또는 **원래 폴더명 접두어**
- 접두어·접미어·자릿수·시작 번호·정렬을 지원하는 **순번 이름짓기**
- 모든 작업의 **실행 전 미리보기와 별도 최종 확인**
- JSON 작업 로그와 **직전 작업 실행 취소(Undo)**
- 숨김·시스템 파일, 심볼릭 링크, 정션, 보호 경로 자동 차단
- Windows 탐색기 **우클릭 메뉴 등록/해제**
- GitHub Releases 기반 **사용자 승인·SHA-256 검증 업데이트**

## 바로 실행

GitHub Releases에서 `FileFlow-Lite.exe` 또는 `FileFlow-Lite-portable.zip`을 받습니다. 설치가 필요 없는 단일 실행 파일입니다.

1. `FileFlow-Lite.exe`를 실행합니다.
2. `폴더 평탄화` 또는 `순번 이름짓기`를 선택합니다.
3. 범위와 규칙을 정한 뒤 `미리보기 만들기`를 누릅니다.
4. 변경 전→후 목록을 확인합니다.
5. `최종 확인…`을 누르고 안전 안내를 확인한 뒤 적용합니다.

기본 동작은 원본을 보존하는 **복사**입니다. 앱 설정에서 탐색기 우클릭 메뉴를 등록할 수 있으며 현재 사용자 전용 등록은 관리자 권한이 필요하지 않습니다.

## 우클릭 통합

- 폴더 우클릭: `FileFlow Lite로 이 폴더 평탄화`
- 폴더 또는 폴더 배경 우클릭: `FileFlow Lite 순번 이름짓기`
- 앱의 `설정 및 업데이트`에서 등록/해제

Windows 11에서는 기존 형식 메뉴가 `더 많은 옵션 표시` 아래에 나타날 수 있습니다. 현재 사용자 레지스트리(`HKCU`)만 사용하므로 관리자 권한이 필요하지 않습니다.

## 안전 동작

- 미리보기 없이 실행할 수 없습니다.
- 실행 직전에 파일 크기와 수정시각을 다시 검사합니다.
- 기존 대상 파일을 덮어쓰지 않습니다.
- 평탄화 중 오류가 나면 완료된 항목을 자동 롤백합니다.
- Undo 전에 모든 대상 상태를 먼저 검사해 부분 실행 취소를 방지합니다.
- 순번 이름 변경은 임시 고유 이름을 거치는 2단계 방식으로 이름 교환도 안전하게 처리합니다.
- 로그는 `%LOCALAPPDATA%\FileFlowLite\logs`에만 저장되며 외부로 전송되지 않습니다.

Undo는 직전 성공 작업만 대상으로 합니다. 작업 후 파일이 수정되었거나 원래 경로가 다른 파일에 의해 점유되면 안전을 위해 중단됩니다.

## 소스에서 실행

Python 3.12 이상과 Tk 지원 Windows Python이 필요합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m fileflow_lite
```

테스트:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

단일 EXE 빌드:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

배포 ZIP과 체크섬 생성:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\package.ps1
```

바탕 화면 바로가기 생성:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\make_shortcut.ps1 -ExePath .\dist\FileFlow-Lite.exe
```

## 업데이트 정책

앱은 사용자가 `업데이트 확인`을 누른 경우에만 GitHub API에 연결합니다. 새 버전 ZIP과 같은 릴리스에 게시된 `SHA256SUMS.txt`를 내려받아 일치할 때만 파일을 유지합니다. 무인 설치나 실행 파일 자동 덮어쓰기는 하지 않습니다.

## 라이선스

MIT License. 빌드 도구와 Python 런타임에는 각각의 오픈소스 라이선스가 적용됩니다.

