namespace FileFlow.Core;

public static class Planner
{
    public static OperationPlan Flatten(
        string source,
        string destination,
        FileAction action = FileAction.Copy,
        bool folderPrefix = false,
        bool deleteEmpty = false,
        IReadOnlySet<string>? extensions = null)
    {
        if (action is not FileAction.Copy and not FileAction.Move)
            throw new SafetyException("처리 방식은 복사 또는 이동이어야 합니다.");
        var (src, dst) = Safety.ValidateFlattenRoots(source, destination);
        var excluded = new List<string>();
        var files = EnumerateFiles(src, excluded).Order(StringComparer.OrdinalIgnoreCase).ToList();
        var occupied = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (Directory.Exists(dst))
            foreach (var entry in Directory.EnumerateFileSystemEntries(dst)) occupied.Add(Safety.Normalize(entry));

        HashSet<string>? normalizedExtensions = null;
        if (extensions is { Count: > 0 })
            normalizedExtensions = extensions.Select(ext => ext.StartsWith('.') ? ext.ToLowerInvariant() : "." + ext.ToLowerInvariant()).ToHashSet(StringComparer.OrdinalIgnoreCase);

        var items = new List<PlanItem>();
        var collisions = 0;
        foreach (var file in files)
        {
            if (normalizedExtensions is not null && !normalizedExtensions.Contains(Path.GetExtension(file)))
            {
                excluded.Add($"{file} — 확장자 필터");
                continue;
            }
            var (target, adjusted) = AvailableDestination(file, dst, occupied, folderPrefix);
            Safety.ValidateDestination(target, dst);
            if (adjusted) collisions++;
            items.Add(new(file, target, action, FileFingerprint.FromPath(file), adjusted ? "이름 충돌 자동 해결" : ""));
        }

        var warnings = new List<string>();
        if (collisions > 0) warnings.Add($"이름 충돌 {collisions}개를 안전하게 조정했습니다.");
        if (excluded.Count > 0) warnings.Add($"보호/필터 항목 {excluded.Count}개를 제외했습니다.");
        return new()
        {
            Kind = OperationKind.Flatten,
            Items = items,
            SourceRoot = src,
            DestinationRoot = dst,
            DeleteEmpty = deleteEmpty && action == FileAction.Move,
            Excluded = excluded,
            Warnings = warnings
        };
    }

    public static OperationPlan SequentialRename(
        IEnumerable<string> selectedFiles,
        string prefix = "",
        string suffix = "",
        int padding = 1,
        int start = 1,
        string sortBy = "name",
        bool descending = false)
    {
        if (padding is < 1 or > 12) throw new SafetyException("번호 자릿수는 1~12 사이여야 합니다.");
        if (start < 0) throw new SafetyException("시작 번호는 0 이상이어야 합니다.");
        Safety.ValidateNamePart(prefix, "접두어");
        Safety.ValidateNamePart(suffix, "접미어");

        var excluded = new List<string>();
        var unique = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var raw in selectedFiles)
        {
            var path = Safety.Normalize(raw);
            if (unique.ContainsKey(path)) continue;
            if (!File.Exists(path)) { excluded.Add($"{path} — 일반 파일이 아님"); continue; }
            var reason = Safety.ExclusionReason(path);
            if (reason is not null) { excluded.Add($"{path} — {reason}"); continue; }
            Safety.ValidateRoot(Path.GetDirectoryName(path)!, true, "파일 위치");
            unique[path] = path;
        }
        var files = unique.Values.ToList();
        if (files.Count == 0) throw new SafetyException("안전하게 이름을 바꿀 수 있는 파일이 없습니다.");

        Comparison<string> comparison = sortBy switch
        {
            "name" => (a, b) => StringComparer.OrdinalIgnoreCase.Compare(Path.GetFileName(a), Path.GetFileName(b)),
            "mtime" => (a, b) => File.GetLastWriteTimeUtc(a).CompareTo(File.GetLastWriteTimeUtc(b)),
            "size" => (a, b) => new FileInfo(a).Length.CompareTo(new FileInfo(b).Length),
            _ => throw new SafetyException("지원하지 않는 정렬 기준입니다.")
        };
        files.Sort(comparison);
        if (descending) files.Reverse();

        var selected = files.ToHashSet(StringComparer.OrdinalIgnoreCase);
        var occupied = new Dictionary<string, HashSet<string>>(StringComparer.OrdinalIgnoreCase);
        foreach (var file in files)
        {
            var parent = Path.GetDirectoryName(file)!;
            if (!occupied.ContainsKey(parent))
                occupied[parent] = Directory.EnumerateFileSystemEntries(parent).Select(Safety.Normalize).Where(path => !selected.Contains(path)).ToHashSet(StringComparer.OrdinalIgnoreCase);
        }
        var reserved = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var items = new List<PlanItem>();
        for (var index = 0; index < files.Count; index++)
        {
            var source = files[index];
            var parent = Path.GetDirectoryName(source)!;
            var number = (start + index).ToString().PadLeft(padding, '0');
            var filename = $"{prefix}{number}{suffix}{Path.GetExtension(source)}";
            Safety.ValidateNamePart(filename, "변경 후 파일명");
            var target = Safety.Normalize(Path.Combine(parent, filename));
            Safety.ValidateDestination(target, parent);
            if (occupied[parent].Contains(target) || !reserved.Add(target))
                throw new SafetyException($"변경 후 이름이 기존 파일과 충돌합니다: {filename}");
            items.Add(new(source, target, FileAction.Rename, FileFingerprint.FromPath(source), source.Equals(target, StringComparison.OrdinalIgnoreCase) ? "변경 없음" : ""));
        }
        return new()
        {
            Kind = OperationKind.Rename,
            Items = items,
            SourceRoot = files.Select(Path.GetDirectoryName).Distinct(StringComparer.OrdinalIgnoreCase).Count() == 1 ? Path.GetDirectoryName(files[0]) : null,
            Excluded = excluded,
            Warnings = excluded.Count > 0 ? [$"보호 항목 {excluded.Count}개를 제외했습니다."] : []
        };
    }

    private static IEnumerable<string> EnumerateFiles(string root, List<string> excluded)
    {
        var stack = new Stack<string>();
        stack.Push(root);
        while (stack.Count > 0)
        {
            var directory = stack.Pop();
            IEnumerable<string> entries;
            try { entries = Directory.EnumerateFileSystemEntries(directory).ToArray(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                excluded.Add($"{directory} — 읽기 실패: {ex.Message}");
                continue;
            }
            foreach (var entry in entries)
            {
                var reason = Safety.ExclusionReason(entry);
                if (reason is not null) { excluded.Add($"{entry} — {reason}"); continue; }
                if (Directory.Exists(entry)) stack.Push(entry);
                else if (File.Exists(entry)) yield return Safety.Normalize(entry);
            }
        }
    }

    private static (string Destination, bool Adjusted) AvailableDestination(string source, string root, HashSet<string> occupied, bool folderPrefix)
    {
        var filename = Path.GetFileName(source);
        var candidate = Safety.Normalize(Path.Combine(root, filename));
        if (occupied.Add(candidate)) return (candidate, false);
        var baseName = Path.GetFileNameWithoutExtension(source);
        if (folderPrefix)
        {
            var folder = new DirectoryInfo(Path.GetDirectoryName(source)!).Name;
            Safety.ValidateNamePart(folder, "폴더명 접두어");
            baseName = $"{folder}_{baseName}";
            candidate = Safety.Normalize(Path.Combine(root, baseName + Path.GetExtension(source)));
            if (occupied.Add(candidate)) return (candidate, true);
        }
        for (var index = 2; ; index++)
        {
            candidate = Safety.Normalize(Path.Combine(root, $"{baseName} ({index}){Path.GetExtension(source)}"));
            if (occupied.Add(candidate)) return (candidate, true);
        }
    }
}
