# FileFlow Lite — Windows 11 Explorer Edition

Windows 11 파일 탐색기의 기본 우클릭 메뉴에 안전한 폴더 평탄화와 일괄 순번 이름짓기를 직접 추가하는 무료 오픈소스 셸 확장입니다. 별도 메인 앱이나 로컬 서버 없이 탐색기에서 선택하고, 짧은 Windows Fluent 미리보기 창에서 확인한 뒤 적용합니다.

> v0.1.0은 파일 엔진을 검증한 별도 앱 프로토타입입니다. v0.2.0부터 탐색기 네이티브 확장형이 기본 제품입니다.

## 주요 기능

- 모든 하위 폴더의 파일을 한 폴더로 **복사 또는 이동**
- 이름 충돌 시 **순번 자동 부여** 또는 **원래 폴더명 접두어**
- 접두어·접미어·자릿수·시작 번호·정렬을 지원하는 **순번 이름짓기**
- 모든 작업의 **실행 전 미리보기와 별도 최종 확인**
- JSON 작업 로그와 **직전 작업 실행 취소(Undo)**
- 숨김·시스템 파일, 심볼릭 링크, 정션, 보호 경로 자동 차단
- Windows 11 **첫 번째 우클릭 메뉴**에 직접 표시되는 현대식 `IExplorerCommand`
- Windows 자체 MSIX 서명 확인과 App Installer 기반 업데이트

## 설치와 사용

GitHub Releases에서 `FileFlow-Lite-Explorer-v0.2.0.zip`을 내려받아 압축을 푼 뒤 `Install-FileFlowLite.cmd`를 한 번 실행합니다. 무료 배포를 위해 자체 서명한 MSIX이므로 최초 설치 시 UAC 관리자 승인이 한 번 필요합니다. 설치기는 공개 인증서를 시스템의 `LocalMachine\\TrustedPeople` 저장소에만 추가하고, 패키지 서명과 인증서 지문이 일치하는지 확인한 뒤 설치합니다. 신뢰 범위가 더 넓은 루트 인증서 저장소에는 추가하지 않습니다.

1. 탐색기에서 폴더 하나를 우클릭해 `폴더 평탄화`를 선택합니다.
2. 또는 여러 파일을 선택해 우클릭하고 `순번 이름짓기`를 선택합니다.
3. Windows 11 스타일 창에서 옵션과 변경 전→후 목록을 확인합니다.
4. `확인하고 적용`을 누른 뒤 최종 안전 안내에서 한 번 더 확인합니다.
5. 필요한 경우 폴더 우클릭 메뉴의 `직전 작업 실행 취소`를 사용합니다.

기본 동작은 원본을 보존하는 **복사**입니다. 우클릭 통합은 MSIX 설치와 함께 등록되며 별도 설정 앱을 열 필요가 없습니다. 설치 후 일반 사용에는 관리자 권한이 필요하지 않습니다.

## 탐색기 통합 구조

- 최소 네이티브 C++ COM DLL이 `IExplorerCommand`만 구현합니다.
- COM DLL은 Windows COM Surrogate에서 활성화되어 관리형 런타임을 `explorer.exe`에 직접 로드하지 않습니다.
- 탐색기 선택 항목은 사용자 전용 임시 파일로 전달되며 작업 프로세스가 읽은 즉시 삭제합니다.
- 파일 스캔과 변경은 .NET 10 WPF 작업 프로세스에서 실행합니다.
- WPF의 공식 Fluent 테마가 시스템 밝기/다크 모드와 강조색을 따릅니다.

MSIX 패키지는 시작 메뉴 항목을 만들지 않습니다. 작업 창은 탐색기 명령을 호출했을 때만 나타납니다.

## 안전 동작

- 미리보기 없이 실행할 수 없습니다.
- 실행 직전에 파일 크기와 수정시각을 다시 검사합니다.
- 기존 대상 파일을 덮어쓰지 않습니다.
- 평탄화 중 오류가 나면 완료된 항목을 자동 롤백합니다.
- Undo 전에 모든 대상 상태를 먼저 검사해 부분 실행 취소를 방지합니다.
- 순번 이름 변경은 임시 고유 이름을 거치는 2단계 방식으로 이름 교환도 안전하게 처리합니다.
- 로그는 `%LOCALAPPDATA%\FileFlowLite\logs`에만 저장되며 외부로 전송되지 않습니다.

Undo는 직전 성공 작업만 대상으로 합니다. 작업 후 파일이 수정되었거나 원래 경로가 다른 파일에 의해 점유되면 안전을 위해 중단됩니다.

## v0.2 소스 빌드

.NET 10 SDK, Visual Studio 2022 C++ Build Tools, Windows 11 SDK, Python과 Pillow가 필요합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-v2.ps1
```

결과물은 `dist-v2`에 생성됩니다. `native/FileFlow.Core.Tests`는 NuGet 테스트 프레임워크 없이 독립적으로 실행 가능한 안전성 회귀 테스트입니다.

## v0.1 프로토타입 실행

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

v0.2는 Windows App Installer가 탐색기 작업 프로세스 실행 시 최대 24시간 간격으로 GitHub Releases의 새 MSIX를 확인합니다. 설치 전 Windows가 게시자 서명을 검증하며, 업데이트를 강제로 막거나 별도 서비스로 파일을 덮어쓰지 않습니다.

## 라이선스

MIT License. 빌드 도구와 Python 런타임에는 각각의 오픈소스 라이선스가 적용됩니다.
