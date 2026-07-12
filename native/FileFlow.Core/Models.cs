namespace FileFlow.Core;

public enum OperationKind { Flatten, Rename }
public enum FileAction { Copy, Move, Rename }

public sealed record FileFingerprint(long Size, long LastWriteUtcTicks)
{
    public static FileFingerprint FromPath(string path)
    {
        var info = new FileInfo(path);
        return new(info.Length, info.LastWriteTimeUtc.Ticks);
    }
}

public sealed record PlanItem(
    string Source,
    string Destination,
    FileAction Action,
    FileFingerprint Fingerprint,
    string Note = "");

public sealed class OperationPlan
{
    public string Id { get; init; } = Guid.NewGuid().ToString("N");
    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;
    public required OperationKind Kind { get; init; }
    public required List<PlanItem> Items { get; init; }
    public string? SourceRoot { get; init; }
    public string? DestinationRoot { get; init; }
    public bool DeleteEmpty { get; init; }
    public List<string> Warnings { get; init; } = [];
    public List<string> Excluded { get; init; } = [];
    public long TotalSize => Items.Sum(item => item.Fingerprint.Size);
}

public sealed record CompletedItem(
    string Source,
    string Destination,
    FileAction Action,
    FileFingerprint DestinationFingerprint);

public sealed class OperationJournal
{
    public int JournalVersion { get; init; } = 2;
    public required string Id { get; init; }
    public required string Status { get; set; }
    public required OperationKind Kind { get; init; }
    public required OperationPlan Plan { get; init; }
    public List<CompletedItem> Completed { get; init; } = [];
    public List<string> DeletedDirectories { get; init; } = [];
    public bool CreatedDestination { get; init; }
    public string? Error { get; set; }
    public List<string> RollbackErrors { get; init; } = [];
    public DateTimeOffset FinishedAt { get; init; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? UndoneAt { get; set; }
}

public sealed class SafetyException(string message) : InvalidOperationException(message);
