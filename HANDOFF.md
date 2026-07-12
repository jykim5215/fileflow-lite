# FileFlow Lite — 프로젝트 인계 문서

## 1. 프로젝트 개요와 목표

FileFlow Lite는 Windows 11 파일 탐색기의 기본 우클릭 메뉴에 파일 정리 기능을 직접 추가하는 무료·오픈소스 x64 셸 확장이다. 별도 대시보드형 앱이나 로컬 서버를 상시 실행하지 않는다. 사용자는 탐색기에서 항목을 선택하고 `폴더 평탄화`, `순번 이름짓기`, `직전 작업 실행 취소`를 호출한다. 파일을 바꾸기 전에는 Windows Fluent 스타일의 짧은 미리보기 창과 별도 최종 확인을 반드시 거친다.

v0.1.0 Python/Tkinter 버전은 파일 엔진과 안전 정책을 검증한 프로토타입으로 보존한다. 최종 제품 방향은 v0.2.0부터 적용된 Windows 11 탐색기 네이티브 확장형이다.

핵심 목표는 다음과 같다.

- 하위 폴더의 파일을 한 폴더로 안전하게 모으는 **폴더 평탄화**
- 여러 파일을 규칙에 따라 연속 번호로 바꾸는 **일괄 순번 이름짓기**
- 모든 변경 전 **미리보기와 명시적 사용자 확인** 강제
- 직전 성공 작업의 **Undo** 및 감사 가능한 로컬 JSON 로그
- 시스템·숨김 파일, 재분석 지점, 보호 경로, 범위 밖 이동과 덮어쓰기 차단
- GitHub Releases와 서명된 MSIX/App Installer를 이용한 무료 업데이트

## 2. 사용자 요구사항과 구현 범위

### 2.1 폴더 평탄화

- 선택한 폴더의 모든 하위 폴더를 재귀 순회한다.
- 기본은 원본을 보존하는 `복사`이며 `이동`도 선택할 수 있다.
- 대상 폴더 기본값은 원본과 같은 위치의 `<원본 폴더명> - 모음`이다.
- 이름 충돌은 `파일 (2).ext` 순번 또는 `원래폴더_파일.ext` 접두어 방식으로 해결한다. 접두어 적용 뒤에도 충돌하면 순번을 추가한다.
- 빈 폴더 삭제는 이동 모드에서만 선택할 수 있다.
- 대상이 원본과 같거나 원본 내부인 경우, 드라이브 루트 또는 Windows 보호 영역인 경우 실행을 차단한다.

### 2.2 일괄 순번 이름짓기

- 탐색기에서 선택한 여러 파일을 이름, 수정일, 크기로 정렬한다.
- 오름차순/내림차순, 접두어, 접미어, 1~12자리 패딩, 0 이상의 시작 번호를 지원한다.
- 확장자는 그대로 유지한다.
- 이름 교환과 순환 변경도 안전하도록 모든 원본을 임시 GUID 이름으로 옮긴 뒤 최종 이름으로 이동하는 2단계 방식을 사용한다.
- 선택 항목이 여러 폴더에 있어도 각 파일은 원래 폴더 안에서만 이름을 바꾼다.

### 2.3 필수 안전장치

- `스캔 → 미리보기 → 별도 최종 확인 → 실행` 순서를 우회할 수 없다.
- 미리보기 뒤 실행 직전에 크기와 UTC 수정시각을 다시 비교한다. 달라졌으면 아무것도 시작하지 않고 재미리보기를 요구한다.
- 기존 파일을 덮어쓰지 않는다.
- 평탄화 도중 실패하면 완료 항목을 역순 롤백한다.
- Undo는 모든 대상의 지문과 원래 경로 점유 여부를 먼저 검사한 뒤에만 실행해 부분 Undo를 방지한다.
- Undo 메뉴를 눌러도 기본값이 `아니요`인 확인창을 먼저 표시한다.
- 숨김·시스템 파일과 폴더, 점으로 시작하는 항목, 심볼릭 링크·정션 등 재분석 지점은 제외한다.
- 로그와 IPC 파일은 `%LOCALAPPDATA%\FileFlowLite` 아래에만 저장하며 외부로 전송하지 않는다.
- 탐색기 선택 IPC는 길이 제한이 있는 바이너리 형식이며, 작업 프로세스가 읽는 즉시 삭제한다.

## 3. 기술 방향과 설계 결정

### 3.1 무료 스택

- **탐색기 셸 처리기:** C++20, Windows SDK, `IExplorerCommand`
- **미리보기/실행 프로세스:** .NET 10, WPF, Microsoft 공식 Fluent 테마
- **파일 엔진:** 별도 NuGet 패키지 없는 C# 표준 라이브러리
- **배포:** Windows SDK MakeAppx/SignTool, 자체 서명 MSIX, App Installer
- **빌드:** Visual Studio 2022 Build Tools, .NET SDK, GitHub Actions
- **자산 생성:** Python/Pillow
- **라이선스:** 프로젝트 MIT, 상용 라이브러리와 유료 런타임 서비스 없음

자체 서명 방식은 무료 배포를 유지하지만 최초 설치 시 공개 인증서를 신뢰시키기 위한 UAC 관리자 승인이 한 번 필요하다. 설치기는 인증서를 `LocalMachine\TrustedPeople`에만 넣고 루트 인증서 저장소는 사용하지 않는다. 설치 후 일반 파일 작업에는 관리자 권한이 필요하지 않다.

### 3.2 아키텍처

1. 탐색기가 MSIX로 등록된 최소 C++ COM 셸 DLL을 COM Surrogate에서 활성화한다.
2. DLL의 `GetState`가 선택 유형만 빠르게 확인해 가능한 명령만 첫 번째 우클릭 메뉴에 표시한다.
3. `Invoke`는 선택 경로를 사용자 전용 IPC 파일로 직렬화하고 인접한 작업 EXE를 실행한다. DLL 안에서는 파일 스캔, 변경, 네트워크 요청을 하지 않는다.
4. WPF 작업 프로세스가 IPC를 검증·삭제하고 백그라운드에서 불변 작업 계획을 생성한다.
5. 사용자가 미리보기와 최종 확인을 승인하면 Executor가 사전조건을 다시 검사하고 작업을 직렬 실행한다.
6. JournalStore가 성공·실패·롤백·Undo 상태를 원자적 JSON으로 기록한다.
7. 완료 후 `SHChangeNotify`로 탐색기를 즉시 갱신한다.

관리형 셸 확장을 `explorer.exe`에 직접 로드하지 않는 이유는 탐색기 안정성과 CLR 버전 충돌 위험을 줄이기 위해서다. 실제 파일 작업을 별도 프로세스로 분리해 셸 DLL의 공격 표면과 실행 시간을 최소화한다.

### 3.3 주요 파일 구조

```text
FileFlow-Lite/
├─ HANDOFF.md
├─ README.md
├─ SECURITY.md
├─ native/
│  ├─ FileFlow.Core/          # 계획, 안전 검사, 실행, 저널, Undo, IPC
│  ├─ FileFlow.Core.Tests/    # NuGet 없는 12개 회귀 테스트 실행기
│  ├─ FileFlow.Worker/        # WPF Fluent 미리보기/확인 창
│  └─ FileFlow.Shell/         # x64 IExplorerCommand COM DLL
├─ packaging/msix/
│  ├─ AppxManifest.xml
│  ├─ FileFlow-Lite.appinstaller
│  ├─ Install-FileFlowLite.cmd/.ps1
│  └─ Uninstall-FileFlowLite.ps1
├─ scripts/
│  ├─ build-v2.ps1
│  └─ generate_msix_assets.py
├─ .github/workflows/native-release.yml
├─ src/, tests/               # v0.1 프로토타입
└─ ui-candidates/             # 최초 디자인 후보 기록
```

`packaging/msix/FileFlow-Lite-Signing.pfx`, `dist-v2`, `build-v2`, C++/C# 빌드 폴더는 Git에 포함하지 않는다. CI 서명 PFX와 암호는 GitHub Actions Secrets에만 저장한다.

## 4. UI/UX 결정

초기 HTML 후보 중 A의 옵션·미리보기 동시 배치와 C의 별도 최종 확인 개념을 선택했지만, 사용자가 별도 앱 같은 대시보드를 원하지 않는다고 명확히 정정했다. v0.2는 다음 원칙으로 다시 설계했다.

- 시작 메뉴 항목, 바탕 화면 바로가기, 메인 대시보드를 만들지 않는다.
- 탐색기 우클릭으로 호출될 때만 작업 창이 나타난다.
- Windows 11 시스템 글꼴, 공식 Fluent 컨트롤, 밝기/다크 테마, 강조색, Mica 배경을 따른다.
- 평탄화와 이름짓기는 필요한 옵션만 한 화면에 표시하며, 옵션 변경 시 미리보기를 자동 갱신한다.
- 상단에는 작업명과 설명, 중앙에는 옵션과 변경 전→후 표, 하단에는 상태와 `취소`/`확인하고 적용`만 둔다.
- 실제 적용 전 별도 확인창에서 작업 종류·수량·경고를 다시 보여준다.
- Undo 가능 기록이 없으면 우클릭 메뉴의 `직전 작업 실행 취소` 자체를 숨긴다.

추가 편의 기능으로 내림차순 정렬, 결과 폴더 자동 기본값, 충돌/제외 요약, 백그라운드 미리보기, 탐색기 즉시 갱신, 시스템 테마 연동을 포함했다. 확장자·크기 필터와 CSV 계획 내보내기는 핵심 안정화 이후 후보이며 현재 UI에는 노출하지 않는다.

## 5. 탐색기 통합과 설치/제거

- 폴더 하나 우클릭: `폴더 평탄화`
- 파일 하나 이상 우클릭: `순번 이름짓기`
- 폴더 우클릭, 성공 저널이 있을 때만: `직전 작업 실행 취소`

등록은 레지스트리 문자열 명령이 아니라 MSIX의 `windows.fileExplorerContextMenus`와 `windows.comServer` 선언으로 수행한다. 패키지는 `AppListEntry="none"`이므로 시작 메뉴에 나타나지 않는다.

배포 ZIP의 `Install-FileFlowLite.cmd`가 원클릭 설치 진입점이다. UAC 승격 후 다음을 수행한다.

1. 포함된 CER의 게시자, 유효기간, MSIX 서명 지문 일치를 검사한다.
2. 공개 인증서를 `LocalMachine\TrustedPeople`에 추가한다.
3. 기존 v0.1 HKCU 컨텍스트 메뉴와 바탕 화면 바로가기를 제거한다.
4. `.appinstaller` 등록을 시도하고, 원격 릴리스가 아직 없으면 로컬 MSIX 설치로 안전하게 대체한다.
5. 탐색기를 재시작한다.

`Uninstall-FileFlowLite.ps1`은 패키지와 정확히 같은 지문의 공개 인증서만 제거한 뒤 탐색기를 재시작한다. 다른 인증서나 레지스트리 키를 광범위하게 지우지 않는다.

## 6. GitHub 배포와 업데이트

- 공개 저장소: `https://github.com/jykim5215/fileflow-lite`
- v0.1.0 릴리스: `https://github.com/jykim5215/fileflow-lite/releases/tag/v0.1.0`
- v0.2 태그가 푸시되면 Windows GitHub Actions가 테스트, 자체 포함 작업 EXE 게시, C++ DLL 빌드, MSIX 생성·서명·타임스탬프, ZIP과 SHA-256 생성을 수행한다.
- CI 액션은 움직이는 태그가 아닌 검증한 커밋 SHA로 고정한다.
- App Installer는 GitHub `releases/latest/download`의 고정 파일명 `FileFlow-Lite.appinstaller`와 `FileFlow-Lite-Explorer.msix`를 사용한다.
- `OnLaunch`는 최대 24시간 간격으로 새 버전을 확인하고 사용자에게 알리며, 백그라운드 업데이트 검사도 선언한다. 새 패키지는 같은 게시자 서명을 가져야 한다.
- 앱 런타임은 로컬 서버나 자체 업데이트 서비스를 띄우지 않는다.

## 7. 검증 기준

- Core 회귀 테스트 12/12 통과: 충돌 처리, 경계 차단, 복사/이동/빈 폴더 Undo, TOCTOU, 부분 실패 롤백, Undo 사전검사, 패딩, 이름 충돌, 이름 교환, 금지 문자.
- WPF x64 자체 포함 단일 EXE 빌드 경고·오류 0.
- C++ x64 Release 빌드 `/W4 /WX`, 경고·오류 0.
- 실제 WPF 렌더 스모크 테스트로 공식 Fluent 테마, 레이아웃, 백그라운드 미리보기 확인.
- NuGet 취약 패키지 조회 결과 0건.
- 최종 MSIX는 DigiCert RFC3161 SHA-256 타임스탬프와 코드 서명을 포함해야 한다.
- MSIX를 풀어 허용된 실행 파일·DLL·매니페스트·PNG 외 개발 파일이 없는지 검사한다.
- 소스·ZIP·MSIX에서 사용자명, 로컬 절대 경로, 토큰, 개인키 패턴이 검출되지 않아야 한다.
- ZIP과 MSIX SHA-256을 `SHA256SUMS.txt`와 다시 대조한다.
- 실제 설치 검증은 `LocalMachine\TrustedPeople` 등록, 패키지 버전, 세 Explorer 명령 표시, 미리보기와 취소, 테스트 폴더 작업 및 Undo 순으로 수행한다.

## 8. 제약 조건과 비목표

- v0.2는 Windows 11 22000 이상, x64 전용이다. Windows 10 레거시 `더 많은 옵션 표시` 메뉴는 지원하지 않는다.
- 네트워크 드라이브와 클라우드 동기화 폴더는 지연·동시 수정·원자성 차이가 있어 별도 검증 전 보장하지 않는다.
- NTFS ACL, ADS, 파일 소유권을 완전 복제하는 백업 프로그램이 아니다.
- 자체 서명 무료 배포는 최초 설치 시 1회 관리자 승인이 필요하다. 일상 사용과 파일 작업은 권한을 우회하지 않는다.
- Codex 자동화 세션은 보안 데스크톱 UAC 창을 승인할 수 없다. 실제 사용자가 설치 CMD를 실행해 승인해야 로컬 설치 통합 검증이 완료된다.
- 직전 작업 Undo는 장기 백업이 아니며 대상이 바뀌면 안전하게 중단한다.

## 9. 현재 상태

**v0.2.0 탐색기 네이티브 구현·로컬/CI 검증·GitHub Release 게시 완료. 실제 사용자 UAC 설치 확인만 남음.**

- C# Core, WPF Worker, C++ Shell, MSIX 매니페스트, 설치/제거, App Installer, CI를 구현했다.
- Core 테스트 12/12, WPF 빌드, C++ `/W4 /WX` 빌드가 통과했다.
- Windows 11 Fluent UI 렌더 스모크 테스트를 통과했다.
- 자체 서명 인증서와 DigiCert 타임스탬프로 로컬 MSIX/ZIP을 생성했다.
- App Installer가 요구하는 인증서 위치를 `LocalMachine\TrustedPeople`로 바로잡고, 최초 설치 1회 UAC 요구를 문서화했다.
- Undo 우클릭 명령에 기본 `아니요` 확인 단계를 추가했다.
- GitHub Actions 의존성을 커밋 SHA로 고정하고 CI 임시 PFX를 사용 직후 삭제하도록 수정했다.
- NuGet 취약 패키지는 0건이다.
- C++ Release DLL의 디버그 경로를 제거했고 ASLR, 고엔트로피 주소, DEP/NX, Control Flow Guard 활성화를 바이너리 헤더에서 확인했다.
- 최종 DLL·EXE·MSIX·ZIP에서 로컬 사용자 경로가 검출되지 않았고, 텍스트/실행 페이로드의 토큰·개인키 패턴 검사도 통과했다.
- 최종 MSIX에는 허용한 실행 파일, DLL, 매니페스트, 아이콘과 Windows 생성 서명 메타데이터만 있으며 개발 파일은 없다.
- 포함 CER과 MSIX 서명 지문이 일치하고 DigiCert 타임스탬프가 존재한다. ZIP/MSIX SHA-256은 `SHA256SUMS.txt`와 일치한다.
- 자동화 세션에서 UAC가 보안 데스크톱으로 전달되지 않아 실제 MSIX 설치는 아직 완료하지 못했다. 사용자가 배포 ZIP의 설치 CMD를 직접 실행하면 검증을 이어갈 수 있다.
- PR `#1`을 병합했고 PR 검증 실행 `29207661308`과 태그 릴리스 실행 `29207762655`가 모두 성공했다.
- v0.2.0 릴리스: `https://github.com/jykim5215/fileflow-lite/releases/tag/v0.2.0`
- 원격 릴리스의 MSIX와 ZIP을 다시 내려받아 게시된 SHA-256과 일치함을 확인했고, `releases/latest/download` App Installer/MSIX URL도 HTTP 200으로 확인했다.
- 기존 v0.1 워크플로가 `v*` 태그에 반응해 올린 구형 EXE/portable ZIP은 v0.2.0 릴리스에서 제거했다. 레거시 워크플로 트리거를 `v0.1.*`로 제한해 재발을 막았다.
- 다음 단계는 사용자가 ZIP의 `Install-FileFlowLite.cmd`를 실행해 UAC를 승인한 뒤 실제 탐색기 메뉴 표시, 테스트 폴더 미리보기·적용·Undo를 확인하는 것이다.
