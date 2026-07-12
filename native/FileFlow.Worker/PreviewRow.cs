namespace FileFlow.Worker;

public sealed record PreviewRow(string Before, string After, string State);
public enum WorkerMode { Flatten, Rename }
