using System.Windows;
using FileFlow.Core;

namespace FileFlow.Worker;

public partial class ConfirmWindow : Window
{
    public ConfirmWindow(OperationPlan plan)
    {
        InitializeComponent();
        var action = plan.Kind == OperationKind.Rename ? "이름 변경" : plan.Items.FirstOrDefault()?.Action == FileAction.Move ? "이동" : "복사";
        SummaryText.Text = $"{plan.Items.Count:N0}개 파일 · {FormatSize(plan.TotalSize)} · {action}\n이 작업은 확인 후 즉시 시작됩니다.";
    }

    private void Apply_Click(object sender, RoutedEventArgs e) { DialogResult = true; Close(); }

    private static string FormatSize(long bytes)
    {
        string[] units = ["B", "KB", "MB", "GB", "TB"];
        var value = (double)bytes;
        var index = 0;
        while (value >= 1024 && index < units.Length - 1) { value /= 1024; index++; }
        return index == 0 ? $"{bytes:N0} B" : $"{value:0.0} {units[index]}";
    }
}
