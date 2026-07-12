#include <windows.h>
#include <shobjidl.h>
#include <shlobj.h>
#include <shlwapi.h>
#include <strsafe.h>
#include <atomic>
#include <cwchar>
#include <new>
#include <string>
#include <vector>

// {6C6D3BD7-0BFC-4FD3-9C8E-7DC724BDA972}
const CLSID CLSID_FileFlowFlatten = {0x6c6d3bd7,0x0bfc,0x4fd3,{0x9c,0x8e,0x7d,0xc7,0x24,0xbd,0xa9,0x72}};
// {1FB0E20E-99E5-4BBD-A4B2-4236A6B405CA}
const CLSID CLSID_FileFlowRename = {0x1fb0e20e,0x99e5,0x4bbd,{0xa4,0xb2,0x42,0x36,0xa6,0xb4,0x05,0xca}};
// {4F3977C0-2F34-40A6-8A86-0BA2D0E78966}
const CLSID CLSID_FileFlowUndo = {0x4f3977c0,0x2f34,0x40a6,{0x8a,0x86,0x0b,0xa2,0xd0,0xe7,0x89,0x66}};

enum class CommandMode { Flatten, Rename, Undo };
static HINSTANCE g_instance = nullptr;
static std::atomic<long> g_objects = 0;

static HRESULT DuplicateString(const wchar_t* value, PWSTR* result)
{
    if (!result) return E_POINTER;
    return SHStrDupW(value, result);
}

static std::wstring ModuleDirectory()
{
    wchar_t path[MAX_PATH]{};
    if (!GetModuleFileNameW(g_instance, path, ARRAYSIZE(path))) return {};
    PathRemoveFileSpecW(path);
    return path;
}

static HRESULT CreateIpcDirectory(std::wstring& directory)
{
    PWSTR localAppData = nullptr;
    HRESULT hr = SHGetKnownFolderPath(FOLDERID_LocalAppData, KF_FLAG_CREATE, nullptr, &localAppData);
    if (FAILED(hr)) return hr;
    directory.assign(localAppData);
    CoTaskMemFree(localAppData);
    directory += L"\\FileFlowLite";
    if (!CreateDirectoryW(directory.c_str(), nullptr) && GetLastError() != ERROR_ALREADY_EXISTS) return HRESULT_FROM_WIN32(GetLastError());
    directory += L"\\ipc";
    if (!CreateDirectoryW(directory.c_str(), nullptr) && GetLastError() != ERROR_ALREADY_EXISTS) return HRESULT_FROM_WIN32(GetLastError());
    return S_OK;
}

static bool UndoAvailable()
{
    PWSTR localAppData = nullptr;
    if (FAILED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &localAppData))) return false;
    std::wstring marker(localAppData);
    CoTaskMemFree(localAppData);
    marker += L"\\FileFlowLite\\undo-v2.available";
    const DWORD attributes = GetFileAttributesW(marker.c_str());
    return attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0;
}

static HRESULT WriteAll(HANDLE file, const void* data, DWORD bytes)
{
    const auto* cursor = static_cast<const BYTE*>(data);
    while (bytes > 0)
    {
        DWORD written = 0;
        if (!WriteFile(file, cursor, bytes, &written, nullptr)) return HRESULT_FROM_WIN32(GetLastError());
        if (written == 0) return HRESULT_FROM_WIN32(ERROR_WRITE_FAULT);
        cursor += written;
        bytes -= written;
    }
    return S_OK;
}

static HRESULT WriteSelectionManifest(IShellItemArray* selection, std::wstring& manifestPath)
{
    if (!selection) return E_INVALIDARG;
    DWORD count = 0;
    HRESULT hr = selection->GetCount(&count);
    if (FAILED(hr)) return hr;
    if (count == 0 || count > 100000) return E_INVALIDARG;

    std::wstring directory;
    hr = CreateIpcDirectory(directory);
    if (FAILED(hr)) return hr;
    GUID id{};
    if (FAILED(CoCreateGuid(&id))) return E_FAIL;
    wchar_t guid[64]{};
    StringFromGUID2(id, guid, ARRAYSIZE(guid));
    for (wchar_t& character : guid) if (character == L'{' || character == L'}') character = L'_';
    manifestPath = directory + L"\\selection-" + guid + L".bin";

    HANDLE file = CreateFileW(manifestPath.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_TEMPORARY | FILE_ATTRIBUTE_NOT_CONTENT_INDEXED, nullptr);
    if (file == INVALID_HANDLE_VALUE) return HRESULT_FROM_WIN32(GetLastError());
    const BYTE magic[8] = {'F','F','L','S','E','L','2',0};
    hr = WriteAll(file, magic, sizeof(magic));
    if (SUCCEEDED(hr)) hr = WriteAll(file, &count, sizeof(count));
    for (DWORD index = 0; SUCCEEDED(hr) && index < count; ++index)
    {
        IShellItem* item = nullptr;
        hr = selection->GetItemAt(index, &item);
        if (FAILED(hr)) break;
        PWSTR path = nullptr;
        hr = item->GetDisplayName(SIGDN_FILESYSPATH, &path);
        item->Release();
        if (FAILED(hr)) break;
        const size_t characters = wcslen(path);
        if (characters == 0 || characters > 32767) hr = E_INVALIDARG;
        else
        {
            const DWORD bytes = static_cast<DWORD>(characters * sizeof(wchar_t));
            hr = WriteAll(file, &bytes, sizeof(bytes));
            if (SUCCEEDED(hr)) hr = WriteAll(file, path, bytes);
        }
        CoTaskMemFree(path);
    }
    if (!FlushFileBuffers(file) && SUCCEEDED(hr)) hr = HRESULT_FROM_WIN32(GetLastError());
    CloseHandle(file);
    if (FAILED(hr)) DeleteFileW(manifestPath.c_str());
    return hr;
}

static HRESULT LaunchWorker(CommandMode mode, IShellItemArray* selection)
{
    const std::wstring directory = ModuleDirectory();
    if (directory.empty()) return E_FAIL;
    const std::wstring worker = directory + L"\\FileFlow.Worker.exe";
    if (GetFileAttributesW(worker.c_str()) == INVALID_FILE_ATTRIBUTES) return HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND);

    std::wstring manifest;
    std::wstring arguments;
    if (mode == CommandMode::Undo) arguments = L" --undo";
    else
    {
        HRESULT hr = WriteSelectionManifest(selection, manifest);
        if (FAILED(hr)) return hr;
        arguments = mode == CommandMode::Flatten ? L" --flatten-manifest \"" : L" --rename-manifest \"";
        arguments += manifest + L"\"";
    }
    std::wstring commandLine = L"\"" + worker + L"\"" + arguments;
    std::vector<wchar_t> mutableCommand(commandLine.begin(), commandLine.end());
    mutableCommand.push_back(L'\0');
    STARTUPINFOW startup{sizeof(startup)};
    PROCESS_INFORMATION process{};
    if (!CreateProcessW(worker.c_str(), mutableCommand.data(), nullptr, nullptr, FALSE, CREATE_UNICODE_ENVIRONMENT, nullptr, directory.c_str(), &startup, &process))
    {
        if (!manifest.empty()) DeleteFileW(manifest.c_str());
        return HRESULT_FROM_WIN32(GetLastError());
    }
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return S_OK;
}

class ExplorerCommand final : public IExplorerCommand
{
public:
    explicit ExplorerCommand(CommandMode mode) : mode_(mode) { ++g_objects; }
    ~ExplorerCommand() { --g_objects; }

    IFACEMETHODIMP QueryInterface(REFIID iid, void** object) override
    {
        if (!object) return E_POINTER;
        *object = nullptr;
        if (iid == IID_IUnknown || iid == IID_IExplorerCommand) *object = static_cast<IExplorerCommand*>(this);
        else return E_NOINTERFACE;
        AddRef();
        return S_OK;
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return static_cast<ULONG>(InterlockedIncrement(&references_)); }
    IFACEMETHODIMP_(ULONG) Release() override
    {
        const long value = InterlockedDecrement(&references_);
        if (value == 0) delete this;
        return static_cast<ULONG>(value);
    }
    IFACEMETHODIMP GetTitle(IShellItemArray*, PWSTR* name) override
    {
        return DuplicateString(mode_ == CommandMode::Flatten ? L"폴더 평탄화" : mode_ == CommandMode::Rename ? L"순번 이름짓기" : L"직전 작업 실행 취소", name);
    }
    IFACEMETHODIMP GetIcon(IShellItemArray*, PWSTR* icon) override
    {
        const std::wstring value = ModuleDirectory() + L"\\FileFlow.Shell.dll,-101";
        return DuplicateString(value.c_str(), icon);
    }
    IFACEMETHODIMP GetToolTip(IShellItemArray*, PWSTR* tooltip) override
    {
        return DuplicateString(mode_ == CommandMode::Flatten ? L"하위 폴더의 파일을 한 곳으로 모읍니다" : mode_ == CommandMode::Rename ? L"선택한 파일에 연속 번호를 붙입니다" : L"직전 FileFlow Lite 작업을 안전하게 되돌립니다", tooltip);
    }
    IFACEMETHODIMP GetCanonicalName(GUID* guid) override
    {
        if (!guid) return E_POINTER;
        *guid = mode_ == CommandMode::Flatten ? CLSID_FileFlowFlatten : mode_ == CommandMode::Rename ? CLSID_FileFlowRename : CLSID_FileFlowUndo;
        return S_OK;
    }
    IFACEMETHODIMP GetState(IShellItemArray* selection, BOOL, EXPCMDSTATE* state) override
    {
        if (!state) return E_POINTER;
        *state = ECS_DISABLED;
        if (mode_ == CommandMode::Undo) { *state = UndoAvailable() ? ECS_ENABLED : ECS_HIDDEN; return S_OK; }
        if (!selection) return S_OK;
        DWORD count = 0;
        if (FAILED(selection->GetCount(&count)) || count == 0) return S_OK;
        if (mode_ == CommandMode::Flatten && count != 1) return S_OK;
        if (mode_ == CommandMode::Rename)
        {
            SFGAOF filesystem = 0;
            SFGAOF folders = 0;
            if (FAILED(selection->GetAttributes(SIATTRIBFLAGS_AND, SFGAO_FILESYSTEM, &filesystem)) || (filesystem & SFGAO_FILESYSTEM) == 0) return S_OK;
            if (FAILED(selection->GetAttributes(SIATTRIBFLAGS_OR, SFGAO_FOLDER, &folders)) || (folders & SFGAO_FOLDER) != 0) return S_OK;
        }
        else
        {
            IShellItem* item = nullptr;
            if (FAILED(selection->GetItemAt(0, &item))) return S_OK;
            SFGAOF attributes = 0;
            const HRESULT hr = item->GetAttributes(SFGAO_FILESYSTEM | SFGAO_FOLDER, &attributes);
            item->Release();
            if (FAILED(hr) || (attributes & (SFGAO_FILESYSTEM | SFGAO_FOLDER)) != (SFGAO_FILESYSTEM | SFGAO_FOLDER)) return S_OK;
        }
        *state = ECS_ENABLED;
        return S_OK;
    }
    IFACEMETHODIMP Invoke(IShellItemArray* selection, IBindCtx*) override { return LaunchWorker(mode_, selection); }
    IFACEMETHODIMP GetFlags(EXPCMDFLAGS* flags) override { if (!flags) return E_POINTER; *flags = ECF_DEFAULT; return S_OK; }
    IFACEMETHODIMP EnumSubCommands(IEnumExplorerCommand**) override { return E_NOTIMPL; }

private:
    long references_ = 1;
    CommandMode mode_;
};

class ClassFactory final : public IClassFactory
{
public:
    explicit ClassFactory(CommandMode mode) : mode_(mode) { ++g_objects; }
    ~ClassFactory() { --g_objects; }
    IFACEMETHODIMP QueryInterface(REFIID iid, void** object) override
    {
        if (!object) return E_POINTER;
        *object = nullptr;
        if (iid == IID_IUnknown || iid == IID_IClassFactory) *object = static_cast<IClassFactory*>(this); else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return static_cast<ULONG>(InterlockedIncrement(&references_)); }
    IFACEMETHODIMP_(ULONG) Release() override { const long value = InterlockedDecrement(&references_); if (!value) delete this; return static_cast<ULONG>(value); }
    IFACEMETHODIMP CreateInstance(IUnknown* outer, REFIID iid, void** object) override
    {
        if (outer) return CLASS_E_NOAGGREGATION;
        auto* command = new (std::nothrow) ExplorerCommand(mode_);
        if (!command) return E_OUTOFMEMORY;
        const HRESULT hr = command->QueryInterface(iid, object);
        command->Release();
        return hr;
    }
    IFACEMETHODIMP LockServer(BOOL lock) override { if (lock) ++g_objects; else --g_objects; return S_OK; }
private:
    long references_ = 1;
    CommandMode mode_;
};

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) { g_instance = instance; DisableThreadLibraryCalls(instance); }
    return TRUE;
}

extern "C" HRESULT __stdcall DllCanUnloadNow() { return g_objects == 0 ? S_OK : S_FALSE; }

extern "C" HRESULT __stdcall DllGetClassObject(REFCLSID clsid, REFIID iid, void** object)
{
    CommandMode mode;
    if (clsid == CLSID_FileFlowFlatten) mode = CommandMode::Flatten;
    else if (clsid == CLSID_FileFlowRename) mode = CommandMode::Rename;
    else if (clsid == CLSID_FileFlowUndo) mode = CommandMode::Undo;
    else return CLASS_E_CLASSNOTAVAILABLE;
    auto* factory = new (std::nothrow) ClassFactory(mode);
    if (!factory) return E_OUTOFMEMORY;
    const HRESULT hr = factory->QueryInterface(iid, object);
    factory->Release();
    return hr;
}
