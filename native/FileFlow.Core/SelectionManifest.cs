using System.Text;

namespace FileFlow.Core;

public static class SelectionManifest
{
    private static readonly byte[] Magic = "FFLSEL2\0"u8.ToArray();

    public static IReadOnlyList<string> ReadAndDelete(string path)
    {
        var fullPath = Safety.Normalize(path);
        var expectedRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FileFlowLite", "ipc");
        if (!Safety.IsWithin(fullPath, expectedRoot)) throw new SafetyException("선택 정보 파일이 허용된 위치를 벗어났습니다.");
        try
        {
            var attributes = File.GetAttributes(fullPath);
            if ((attributes & FileAttributes.ReparsePoint) != 0) throw new SafetyException("선택 정보 파일이 안전하지 않습니다.");
            using var stream = new FileStream(fullPath, FileMode.Open, FileAccess.Read, FileShare.None);
            using var reader = new BinaryReader(stream, Encoding.Unicode, true);
            if (!reader.ReadBytes(Magic.Length).SequenceEqual(Magic)) throw new SafetyException("선택 정보 형식이 올바르지 않습니다.");
            var count = reader.ReadInt32();
            if (count is < 1 or > 100_000) throw new SafetyException("선택 항목 수가 허용 범위를 벗어났습니다.");
            var paths = new List<string>(count);
            for (var index = 0; index < count; index++)
            {
                var bytes = reader.ReadInt32();
                if (bytes is < 2 or > 65534 || bytes % 2 != 0) throw new SafetyException("선택 경로 길이가 올바르지 않습니다.");
                var data = reader.ReadBytes(bytes);
                if (data.Length != bytes) throw new EndOfStreamException();
                paths.Add(Safety.Normalize(Encoding.Unicode.GetString(data)));
            }
            return paths;
        }
        finally
        {
            try { File.Delete(fullPath); } catch (IOException) { }
        }
    }

    public static void WriteForTests(string path, IEnumerable<string> paths)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        using var writer = new BinaryWriter(stream, Encoding.Unicode, true);
        writer.Write(Magic);
        var list = paths.ToList();
        writer.Write(list.Count);
        foreach (var item in list)
        {
            var bytes = Encoding.Unicode.GetBytes(item);
            writer.Write(bytes.Length);
            writer.Write(bytes);
        }
    }
}
