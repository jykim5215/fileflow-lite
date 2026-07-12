using FileFlow.Core;

var tests = new List<(string Name, Action Run)>
{
    ("flatten collision", FlattenCollision),
    ("flatten prefix", FlattenPrefix),
    ("target inside source blocked", TargetInsideSource),
    ("copy undo", CopyUndo),
    ("move delete empty undo", MoveUndo),
    ("changed source blocked", ChangedSource),
    ("partial copy rollback", PartialCopyRollback),
    ("undo precheck", UndoPrecheck),
    ("rename padding", RenamePadding),
    ("rename collision", RenameCollision),
    ("rename swap undo", RenameSwap),
    ("invalid prefix", InvalidPrefix)
};
var failures = 0;
foreach (var test in tests)
{
    try { test.Run(); Console.WriteLine($"PASS {test.Name}"); }
    catch (Exception ex) { failures++; Console.Error.WriteLine($"FAIL {test.Name}: {ex}"); }
}
Console.WriteLine($"{tests.Count - failures}/{tests.Count} tests passed");
return failures == 0 ? 0 : 1;

static Workspace NewWorkspace() => new();
static void FlattenCollision()
{
    using var w = NewWorkspace(); w.Write("src/a/x.txt", "a"); w.Write("src/b/x.txt", "b");
    var plan = Planner.Flatten(w.Path("src"), w.Path("out"));
    Equal(2, plan.Items.Count); True(plan.Items.Any(i => i.Destination.EndsWith("x (2).txt")));
}
static void FlattenPrefix()
{
    using var w = NewWorkspace(); w.Write("src/a/x.txt", "a"); w.Write("src/b/x.txt", "b");
    var plan = Planner.Flatten(w.Path("src"), w.Path("out"), folderPrefix: true);
    True(plan.Items.Any(i => System.IO.Path.GetFileName(i.Destination).StartsWith("a_") || System.IO.Path.GetFileName(i.Destination).StartsWith("b_")));
}
static void TargetInsideSource()
{
    using var w = NewWorkspace(); Directory.CreateDirectory(w.Path("src"));
    Throws<SafetyException>(() => Planner.Flatten(w.Path("src"), w.Path("src/out")));
}
static void CopyUndo()
{
    using var w = NewWorkspace(); var source = w.Write("src/a.txt", "hello");
    var plan = Planner.Flatten(w.Path("src"), w.Path("out")); Executor.Execute(plan);
    True(File.Exists(w.Path("out/a.txt"))); Equal(1, Executor.UndoLatest()); True(File.Exists(source)); True(!File.Exists(w.Path("out/a.txt")));
}
static void MoveUndo()
{
    using var w = NewWorkspace(); var source = w.Write("src/a/b.txt", "hello");
    Executor.Execute(Planner.Flatten(w.Path("src"), w.Path("out"), FileAction.Move, deleteEmpty: true));
    True(!File.Exists(source)); Equal(1, Executor.UndoLatest()); True(File.Exists(source));
}
static void ChangedSource()
{
    using var w = NewWorkspace(); var source = w.Write("src/a.txt", "before");
    var plan = Planner.Flatten(w.Path("src"), w.Path("out")); File.WriteAllText(source, "changed and longer");
    Throws<SafetyException>(() => Executor.Execute(plan));
}
static void PartialCopyRollback()
{
    using var w = NewWorkspace(); w.Write("src/a.txt", "a"); w.Write("src/b.txt", "b");
    var plan = Planner.Flatten(w.Path("src"), w.Path("out"));
    var second = plan.Items[1].Destination;
    var reporter = new Reporter(value => { if (value.Current == 1) File.WriteAllText(second, "occupied"); });
    Throws<SafetyException>(() => Executor.Execute(plan, reporter));
    True(!File.Exists(plan.Items[0].Destination));
    Equal("occupied", File.ReadAllText(second));
    True(File.Exists(plan.Items[0].Source)); True(File.Exists(plan.Items[1].Source));
}
static void UndoPrecheck()
{
    using var w = NewWorkspace(); w.Write("src/a.txt", "a"); w.Write("src/b.txt", "b");
    var plan = Planner.Flatten(w.Path("src"), w.Path("out")); Executor.Execute(plan);
    File.WriteAllText(plan.Items[0].Destination, "edited and longer");
    Throws<SafetyException>(() => Executor.UndoLatest());
    True(File.Exists(plan.Items[0].Destination)); True(File.Exists(plan.Items[1].Destination));
}
static void RenamePadding()
{
    using var w = NewWorkspace(); var b = w.Write("files/b.png", "bb"); var a = w.Write("files/a.txt", "a");
    var plan = Planner.SequentialRename([b, a], "item-", padding: 3, start: 7);
    Equal("item-007.txt", System.IO.Path.GetFileName(plan.Items[0].Destination)); Equal("item-008.png", System.IO.Path.GetFileName(plan.Items[1].Destination));
}
static void RenameCollision()
{
    using var w = NewWorkspace(); var a = w.Write("files/a.txt", "a"); w.Write("files/01.txt", "occupied");
    Throws<SafetyException>(() => Planner.SequentialRename([a], padding: 2));
}
static void RenameSwap()
{
    using var w = NewWorkspace(); var one = w.Write("files/1.txt", "one"); var two = w.Write("files/2.txt", "two");
    var plan = Planner.SequentialRename([two, one], padding: 1, start: 1, descending: true); Executor.Execute(plan);
    Equal("two", File.ReadAllText(one)); Equal("one", File.ReadAllText(two)); Executor.UndoLatest();
    Equal("one", File.ReadAllText(one)); Equal("two", File.ReadAllText(two));
}
static void InvalidPrefix()
{
    using var w = NewWorkspace(); var a = w.Write("files/a.txt", "a");
    Throws<SafetyException>(() => Planner.SequentialRename([a], "bad/name"));
}

static void True(bool value) { if (!value) throw new Exception("assert true failed"); }
static void Equal<T>(T expected, T actual) where T : notnull { if (!EqualityComparer<T>.Default.Equals(expected, actual)) throw new Exception($"expected {expected}, got {actual}"); }
static void Throws<T>(Action action) where T : Exception { try { action(); } catch (T) { return; } throw new Exception($"expected {typeof(T).Name}"); }

sealed class Workspace : IDisposable
{
    private readonly string _root = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "FileFlowCoreTests", Guid.NewGuid().ToString("N"));
    private readonly string? _previous;
    public Workspace()
    {
        Directory.CreateDirectory(_root);
        _previous = Environment.GetEnvironmentVariable("FILEFLOW_TEST_APPDATA");
        Environment.SetEnvironmentVariable("FILEFLOW_TEST_APPDATA", Path("appdata"));
    }
    public string Path(string relative) => System.IO.Path.Combine(_root, relative.Replace('/', System.IO.Path.DirectorySeparatorChar));
    public string Write(string relative, string content)
    {
        var path = Path(relative); Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path)!); File.WriteAllText(path, content); return path;
    }
    public void Dispose()
    {
        Environment.SetEnvironmentVariable("FILEFLOW_TEST_APPDATA", _previous);
        try { Directory.Delete(_root, true); } catch (IOException) { }
    }
}

sealed class Reporter(Action<(int Current, int Total, string Name)> report) : IProgress<(int Current, int Total, string Name)>
{
    public void Report((int Current, int Total, string Name) value) => report(value);
}
