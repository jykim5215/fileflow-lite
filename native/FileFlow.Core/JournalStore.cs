using System.Text.Json;

namespace FileFlow.Core;

public static class JournalStore
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.General)
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    public static string AppDataDirectory
    {
        get
        {
            var testRoot = Environment.GetEnvironmentVariable("FILEFLOW_TEST_APPDATA");
            var root = string.IsNullOrWhiteSpace(testRoot)
                ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FileFlowLite")
                : Safety.Normalize(testRoot);
            Directory.CreateDirectory(root);
            return root;
        }
    }

    public static string LogDirectory
    {
        get
        {
            var path = Path.Combine(AppDataDirectory, "logs");
            Directory.CreateDirectory(path);
            return path;
        }
    }

    public static string Write(OperationJournal journal)
    {
        var path = Path.Combine(LogDirectory, $"{journal.Id}.json");
        AtomicWrite(path, journal);
        AtomicWrite(Path.Combine(AppDataDirectory, "latest-v2.json"), journal);
        var marker = Path.Combine(AppDataDirectory, "undo-v2.available");
        if (journal.Status == "success" && journal.UndoneAt is null)
            File.WriteAllText(marker, journal.Id);
        else
            File.Delete(marker);
        return path;
    }

    public static OperationJournal? LoadLatest()
    {
        var path = Path.Combine(AppDataDirectory, "latest-v2.json");
        if (!File.Exists(path)) return null;
        try
        {
            var journal = JsonSerializer.Deserialize<OperationJournal>(File.ReadAllText(path), JsonOptions);
            return journal is { Status: "success", UndoneAt: null } ? journal : null;
        }
        catch (JsonException) { return null; }
        catch (IOException) { return null; }
    }

    private static void AtomicWrite(string path, OperationJournal journal)
    {
        var temporary = path + ".tmp";
        var json = JsonSerializer.Serialize(journal, JsonOptions);
        using (var stream = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
        using (var writer = new StreamWriter(stream, new System.Text.UTF8Encoding(false)))
        {
            writer.Write(json);
            writer.Flush();
            stream.Flush(true);
        }
        File.Move(temporary, path, true);
    }
}
