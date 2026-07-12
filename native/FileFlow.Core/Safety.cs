using System.Text.RegularExpressions;

namespace FileFlow.Core;

public static partial class Safety
{
    private static readonly string[] ReservedNames =
    [
        "CON", "PRN", "AUX", "NUL",
        .. Enumerable.Range(1, 9).Select(i => $"COM{i}"),
        .. Enumerable.Range(1, 9).Select(i => $"LPT{i}")
    ];

    public static string Normalize(string path) =>
        Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));

    public static bool IsWithin(string path, string root)
    {
        var candidate = Normalize(path);
        var boundary = Normalize(root);
        return candidate.Equals(boundary, StringComparison.OrdinalIgnoreCase)
            || candidate.StartsWith(boundary + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
    }

    public static string ValidateRoot(string path, bool mustExist, string label)
    {
        if (string.IsNullOrWhiteSpace(path))
            throw new SafetyException($"{label} 폴더를 선택해 주세요.");
        var root = Normalize(path);
        if (mustExist && !Directory.Exists(root))
            throw new SafetyException($"{label} 폴더가 존재하지 않습니다.");
        if (Path.GetPathRoot(root)?.Equals(root, StringComparison.OrdinalIgnoreCase) == true)
            throw new SafetyException($"드라이브 루트는 {label} 폴더로 사용할 수 없습니다.");
        foreach (var protectedRoot in ProtectedRoots())
        {
            if (IsWithin(root, protectedRoot))
                throw new SafetyException($"Windows 보호 영역은 {label} 폴더로 사용할 수 없습니다.");
        }
        return root;
    }

    public static (string Source, string Destination) ValidateFlattenRoots(string source, string destination)
    {
        var src = ValidateRoot(source, true, "원본");
        var dst = ValidateRoot(destination, false, "대상");
        if (src.Equals(dst, StringComparison.OrdinalIgnoreCase))
            throw new SafetyException("원본과 대상 폴더는 서로 달라야 합니다.");
        if (IsWithin(dst, src))
            throw new SafetyException("대상 폴더를 원본 폴더 안에 둘 수 없습니다.");
        if (File.Exists(dst))
            throw new SafetyException("대상 경로가 폴더가 아닙니다.");
        var parent = Path.GetDirectoryName(dst);
        if (parent is null || !Directory.Exists(parent))
            throw new SafetyException("대상 폴더의 상위 폴더가 존재하지 않습니다.");
        return (src, dst);
    }

    public static string? ExclusionReason(string path)
    {
        try
        {
            var attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.ReparsePoint) != 0) return "연결된 폴더/재분석 지점";
            if ((attributes & FileAttributes.System) != 0) return "시스템 파일";
            if ((attributes & FileAttributes.Hidden) != 0 || Path.GetFileName(path).StartsWith('.')) return "숨김 파일";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return $"읽기 오류: {ex.Message}";
        }
        return null;
    }

    public static string ValidateNamePart(string value, string label)
    {
        if (value.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
            throw new SafetyException($"{label}에 Windows 파일명 금지 문자가 있습니다.");
        if (value.EndsWith(' ') || value.EndsWith('.'))
            throw new SafetyException($"{label}은 공백이나 마침표로 끝날 수 없습니다.");
        if (ReservedNames.Contains(value, StringComparer.OrdinalIgnoreCase))
            throw new SafetyException($"{label}에 Windows 예약 이름을 사용할 수 없습니다.");
        return value;
    }

    public static void ValidateDestination(string path, string root)
    {
        if (!IsWithin(path, root))
            throw new SafetyException("계획된 대상 경로가 허용된 폴더를 벗어났습니다.");
        if (path.Length >= 240)
            throw new SafetyException("안전한 Windows 경로 길이를 초과합니다.");
    }

    private static IEnumerable<string> ProtectedRoots()
    {
        var names = new[] { "WINDIR", "ProgramFiles", "ProgramFiles(x86)", "ProgramData" };
        foreach (var name in names)
        {
            var value = Environment.GetEnvironmentVariable(name);
            if (!string.IsNullOrWhiteSpace(value)) yield return Normalize(value);
        }
    }
}
