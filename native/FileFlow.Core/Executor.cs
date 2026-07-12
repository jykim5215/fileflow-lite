namespace FileFlow.Core;

public static class Executor
{
    public static string Execute(OperationPlan plan, IProgress<(int Current, int Total, string Name)>? progress = null)
    {
        if (plan.Items.Count == 0) throw new SafetyException("적용할 파일이 없습니다.");
        var completed = new List<CompletedItem>();
        var createdDestination = false;
        try
        {
            if (plan.Kind == OperationKind.Rename)
                completed.AddRange(ExecuteRename(plan, progress));
            else
            {
                var destinationRoot = plan.DestinationRoot ?? throw new SafetyException("대상 폴더 정보가 없습니다.");
                if (!Directory.Exists(destinationRoot))
                {
                    Directory.CreateDirectory(destinationRoot);
                    createdDestination = true;
                }
                for (var index = 0; index < plan.Items.Count; index++)
                {
                    var item = plan.Items[index];
                    VerifySource(item);
                    VerifyBoundary(plan, item);
                    if (File.Exists(item.Destination) || Directory.Exists(item.Destination))
                        throw new SafetyException($"대상 파일이 이미 존재합니다: {Path.GetFileName(item.Destination)}");
                    switch (item.Action)
                    {
                        case FileAction.Copy: File.Copy(item.Source, item.Destination, false); break;
                        case FileAction.Move: File.Move(item.Source, item.Destination, false); break;
                        default: throw new SafetyException("지원하지 않는 작업입니다.");
                    }
                    completed.Add(new(item.Source, item.Destination, item.Action, FileFingerprint.FromPath(item.Destination)));
                    progress?.Report((index + 1, plan.Items.Count, Path.GetFileName(item.Destination)));
                }
            }
            var deletedDirectories = plan.DeleteEmpty && plan.SourceRoot is not null ? DeleteEmptySubdirectories(plan.SourceRoot) : [];
            var journal = new OperationJournal
            {
                Id = plan.Id,
                Status = "success",
                Kind = plan.Kind,
                Plan = plan,
                Completed = completed,
                DeletedDirectories = deletedDirectories,
                CreatedDestination = createdDestination
            };
            return JournalStore.Write(journal);
        }
        catch (Exception error)
        {
            var rollbackErrors = plan.Kind == OperationKind.Flatten ? RollbackFlatten(completed) : [];
            if (createdDestination && plan.DestinationRoot is not null)
            {
                try { Directory.Delete(plan.DestinationRoot); } catch (IOException) { }
            }
            JournalStore.Write(new()
            {
                Id = plan.Id,
                Status = "failed",
                Kind = plan.Kind,
                Plan = plan,
                Completed = completed,
                CreatedDestination = createdDestination,
                Error = error.Message,
                RollbackErrors = rollbackErrors
            });
            if (rollbackErrors.Count > 0)
                throw new InvalidOperationException($"{error.Message}\n자동 롤백 확인 필요: {string.Join("; ", rollbackErrors)}", error);
            throw;
        }
    }

    public static int UndoLatest(IProgress<(int Current, int Total, string Name)>? progress = null)
    {
        var journal = JournalStore.LoadLatest() ?? throw new SafetyException("실행 취소할 직전 작업이 없습니다.");
        var completed = journal.Completed;
        if (journal.Kind == OperationKind.Rename)
            UndoRename(completed);
        else
        {
            foreach (var item in completed)
            {
                if (!File.Exists(item.Destination) || !Matches(item.Destination, item.DestinationFingerprint))
                    throw new SafetyException($"Undo 대상이 변경되었습니다: {Path.GetFileName(item.Destination)}");
                if (item.Action == FileAction.Move && (File.Exists(item.Source) || Directory.Exists(item.Source)))
                    throw new SafetyException($"원래 위치가 이미 사용 중입니다: {item.Source}");
            }
            foreach (var directory in journal.DeletedDirectories.AsEnumerable().Reverse()) Directory.CreateDirectory(directory);
            for (var index = 0; index < completed.Count; index++)
            {
                var item = completed[completed.Count - 1 - index];
                if (item.Action == FileAction.Copy) File.Delete(item.Destination);
                else
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(item.Source)!);
                    File.Move(item.Destination, item.Source, false);
                }
                progress?.Report((index + 1, completed.Count, Path.GetFileName(item.Source)));
            }
            if (journal.CreatedDestination && journal.Plan.DestinationRoot is not null)
            {
                try { Directory.Delete(journal.Plan.DestinationRoot); } catch (IOException) { }
            }
        }
        journal.UndoneAt = DateTimeOffset.UtcNow;
        journal.Status = "undone";
        JournalStore.Write(journal);
        return completed.Count;
    }

    private static IEnumerable<CompletedItem> ExecuteRename(OperationPlan plan, IProgress<(int, int, string)>? progress)
    {
        var active = plan.Items.Where(item => !item.Source.Equals(item.Destination, StringComparison.OrdinalIgnoreCase)).ToList();
        foreach (var item in active) { VerifySource(item); VerifyBoundary(plan, item); }
        var sourceSet = active.Select(item => item.Source).ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (var item in active)
            if (File.Exists(item.Destination) && !sourceSet.Contains(item.Destination))
                throw new SafetyException($"변경 후 파일명이 이미 존재합니다: {Path.GetFileName(item.Destination)}");

        var staged = new List<(PlanItem Item, string Temporary)>();
        var completed = new List<(PlanItem Item, string Current)>();
        try
        {
            foreach (var item in active)
            {
                var temporary = Path.Combine(Path.GetDirectoryName(item.Source)!, $".fileflow-stage-{Guid.NewGuid():N}.tmp");
                File.Move(item.Source, temporary, false);
                staged.Add((item, temporary));
            }
            for (var index = 0; index < staged.Count; index++)
            {
                var entry = staged[index];
                File.Move(entry.Temporary, entry.Item.Destination, false);
                completed.Add((entry.Item, entry.Item.Destination));
                progress?.Report((index + 1, staged.Count, Path.GetFileName(entry.Item.Destination)));
            }
        }
        catch
        {
            var completedItems = completed.Select(entry => entry.Item).ToHashSet();
            var locations = staged.Select(entry => (entry.Item, completedItems.Contains(entry.Item) ? entry.Item.Destination : entry.Temporary)).ToList();
            RollbackRename(locations);
            throw;
        }
        return active.Select(item => new CompletedItem(item.Source, item.Destination, FileAction.Rename, FileFingerprint.FromPath(item.Destination))).ToList();
    }

    private static void UndoRename(List<CompletedItem> completed)
    {
        foreach (var item in completed)
            if (!File.Exists(item.Destination) || !Matches(item.Destination, item.DestinationFingerprint))
                throw new SafetyException($"Undo 대상이 변경되었습니다: {Path.GetFileName(item.Destination)}");
        var destinations = completed.Select(item => item.Destination).ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (var item in completed)
            if ((File.Exists(item.Source) || Directory.Exists(item.Source)) && !destinations.Contains(item.Source))
                throw new SafetyException($"원래 파일명이 이미 사용 중입니다: {Path.GetFileName(item.Source)}");
        var parked = new List<(string Temporary, CompletedItem Item)>();
        try
        {
            foreach (var item in completed)
            {
                var temporary = Path.Combine(Path.GetDirectoryName(item.Destination)!, $".fileflow-undo-{Guid.NewGuid():N}.tmp");
                File.Move(item.Destination, temporary, false);
                parked.Add((temporary, item));
            }
        }
        catch
        {
            foreach (var entry in parked.AsEnumerable().Reverse())
                if (File.Exists(entry.Temporary) && !File.Exists(entry.Item.Destination)) File.Move(entry.Temporary, entry.Item.Destination, false);
            throw;
        }

        var restored = new List<(CompletedItem Item, string Current)>();
        try
        {
            foreach (var entry in parked)
            {
                File.Move(entry.Temporary, entry.Item.Source, false);
                restored.Add((entry.Item, entry.Item.Source));
            }
        }
        catch
        {
            var restoredSet = restored.Select(entry => entry.Item).ToHashSet();
            var current = parked.Select(entry => (entry.Item, restoredSet.Contains(entry.Item) ? entry.Item.Source : entry.Temporary)).ToList();
            var rollback = new List<(string Temporary, string Destination)>();
            foreach (var entry in current)
            {
                if (!File.Exists(entry.Item2)) continue;
                var temporary = Path.Combine(Path.GetDirectoryName(entry.Item.Destination)!, $".fileflow-undo-rollback-{Guid.NewGuid():N}.tmp");
                File.Move(entry.Item2, temporary, false);
                rollback.Add((temporary, entry.Item.Destination));
            }
            foreach (var entry in rollback) File.Move(entry.Temporary, entry.Destination, false);
            throw;
        }
    }

    private static void RollbackRename(IEnumerable<(PlanItem Item, string Current)> locations)
    {
        var parked = new List<(string Temporary, string Source)>();
        foreach (var (item, current) in locations)
        {
            if (!File.Exists(current)) continue;
            var temporary = Path.Combine(Path.GetDirectoryName(item.Source)!, $".fileflow-rollback-{Guid.NewGuid():N}.tmp");
            File.Move(current, temporary, false);
            parked.Add((temporary, item.Source));
        }
        foreach (var entry in parked)
        {
            if (File.Exists(entry.Source)) throw new IOException($"롤백 대상이 이미 존재합니다: {entry.Source}");
            File.Move(entry.Temporary, entry.Source, false);
        }
    }

    private static List<string> RollbackFlatten(IEnumerable<CompletedItem> completed)
    {
        var errors = new List<string>();
        foreach (var item in completed.Reverse())
        {
            try
            {
                if (!File.Exists(item.Destination) || !Matches(item.Destination, item.DestinationFingerprint))
                    throw new SafetyException($"롤백 대상 상태가 달라졌습니다: {item.Destination}");
                if (item.Action == FileAction.Copy) File.Delete(item.Destination);
                else
                {
                    if (File.Exists(item.Source)) throw new SafetyException($"롤백 원본 위치가 사용 중입니다: {item.Source}");
                    Directory.CreateDirectory(Path.GetDirectoryName(item.Source)!);
                    File.Move(item.Destination, item.Source, false);
                }
            }
            catch (Exception ex) { errors.Add(ex.Message); }
        }
        return errors;
    }

    private static void VerifySource(PlanItem item)
    {
        if (!File.Exists(item.Source) || Safety.ExclusionReason(item.Source) is not null)
            throw new SafetyException($"원본 파일이 없거나 안전하지 않습니다: {item.Source}");
        if (!Matches(item.Source, item.Fingerprint))
            throw new SafetyException($"미리보기 후 파일이 변경되었습니다: {Path.GetFileName(item.Source)}");
    }

    private static void VerifyBoundary(OperationPlan plan, PlanItem item)
    {
        if (plan.Kind == OperationKind.Flatten)
            Safety.ValidateDestination(item.Destination, plan.DestinationRoot ?? throw new SafetyException("대상 폴더 정보가 없습니다."));
        else
            Safety.ValidateDestination(item.Destination, Path.GetDirectoryName(item.Source)!);
    }

    private static bool Matches(string path, FileFingerprint fingerprint)
    {
        try { return FileFingerprint.FromPath(path) == fingerprint; }
        catch (IOException) { return false; }
        catch (UnauthorizedAccessException) { return false; }
    }

    private static List<string> DeleteEmptySubdirectories(string root)
    {
        var removed = new List<string>();
        var discovered = new List<string>();
        var stack = new Stack<string>();
        stack.Push(root);
        while (stack.Count > 0)
        {
            var current = stack.Pop();
            IEnumerable<string> children;
            try { children = Directory.EnumerateDirectories(current).ToArray(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { continue; }
            foreach (var child in children)
            {
                try
                {
                    if ((File.GetAttributes(child) & FileAttributes.ReparsePoint) != 0) continue;
                    discovered.Add(child);
                    stack.Push(child);
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
            }
        }
        foreach (var directory in discovered.OrderByDescending(path => path.Length))
        {
            try
            {
                Directory.Delete(directory, false);
                removed.Add(directory);
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
        return removed;
    }
}
