using System.Collections.ObjectModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Threading;
using FileFlow.Core;
using Microsoft.Win32;

namespace FileFlow.Worker;

public partial class MainWindow : Window
{
    private readonly WorkerMode _mode;
    private readonly IReadOnlyList<string> _selection;
    private readonly ObservableCollection<PreviewRow> _rows = [];
    private OperationPlan? _plan;
    private bool _ready;
    private CancellationTokenSource? _previewDelay;

    public MainWindow(WorkerMode mode, IReadOnlyList<string> selection)
    {
        _mode = mode;
        _selection = selection;
        InitializeComponent();
        PreviewGrid.ItemsSource = _rows;
        ConfigureMode();
        Loaded += async (_, _) =>
        {
            _ready = true;
            await RefreshPreviewAsync();
        };
        SourceInitialized += (_, _) => ApplyWindowsBackdrop();
    }

    private void ConfigureMode()
    {
        if (_mode == WorkerMode.Flatten)
        {
            if (_selection.Count != 1 || !Directory.Exists(_selection[0])) throw new SafetyException("평탄화할 폴더 하나를 선택해 주세요.");
            Title = "폴더 평탄화 — FileFlow Lite";
            TitleText.Text = "폴더 평탄화";
            SubtitleText.Text = "하위 폴더의 파일을 한 위치에서 바로 볼 수 있도록 모읍니다.";
            var source = Safety.Normalize(_selection[0]);
            SourcePathBox.Text = source;
            var parent = Path.GetDirectoryName(source)!;
            DestinationPathBox.Text = Path.Combine(parent, Path.GetFileName(source) + " - 모음");
        }
        else
        {
            if (_selection.Count == 0) throw new SafetyException("이름을 바꿀 파일을 선택해 주세요.");
            Title = "순번 이름짓기 — FileFlow Lite";
            TitleText.Text = "순번 이름짓기";
            SubtitleText.Text = $"파일 탐색기에서 선택한 {_selection.Count:N0}개 파일의 확장자를 유지합니다.";
            FlattenOptions.Visibility = Visibility.Collapsed;
            RenameOptions.Visibility = Visibility.Visible;
        }
    }

    private async Task RefreshPreviewAsync()
    {
        if (!_ready) return;
        _previewDelay?.Cancel();
        var cancellation = _previewDelay = new CancellationTokenSource();
        try
        {
            await Task.Delay(160, cancellation.Token);
            StatusText.Text = "파일 상태를 확인하는 중…";
            ApplyButton.IsEnabled = false;
            var planFactory = CapturePlanFactory();
            var plan = await Task.Run(planFactory, cancellation.Token);
            if (cancellation.IsCancellationRequested) return;
            _plan = plan;
            _rows.Clear();
            foreach (var item in plan.Items)
            {
                var before = _mode == WorkerMode.Flatten && plan.SourceRoot is not null ? Path.GetRelativePath(plan.SourceRoot, item.Source) : Path.GetFileName(item.Source);
                var after = _mode == WorkerMode.Flatten ? Path.GetFileName(item.Destination) : Path.GetFileName(item.Destination);
                _rows.Add(new(before, after, string.IsNullOrEmpty(item.Note) ? ActionText(item.Action) : item.Note));
            }
            SummaryText.Text = $"{plan.Items.Count:N0}개 · {FormatSize(plan.TotalSize)} · 제외 {plan.Excluded.Count:N0}개";
            WarningText.Text = string.Join("  ", plan.Warnings);
            WarningBar.Visibility = plan.Warnings.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
            StatusText.Text = "아직 파일은 변경되지 않았습니다.";
            ApplyButton.IsEnabled = plan.Items.Count > 0;
        }
        catch (OperationCanceledException) { }
        catch (Exception ex)
        {
            _plan = null;
            _rows.Clear();
            SummaryText.Text = "미리보기를 만들 수 없음";
            WarningText.Text = ex.Message;
            WarningBar.Visibility = Visibility.Visible;
            StatusText.Text = "옵션을 확인해 주세요.";
            ApplyButton.IsEnabled = false;
        }
    }

    private Func<OperationPlan> CapturePlanFactory()
    {
        if (_mode == WorkerMode.Flatten)
        {
            var source = SourcePathBox.Text;
            var destination = DestinationPathBox.Text;
            var action = TransferModeBox.SelectedIndex == 0 ? FileAction.Copy : FileAction.Move;
            var folderPrefix = CollisionModeBox.SelectedIndex == 1;
            var deleteEmpty = DeleteEmptyBox.IsChecked == true;
            return () => Planner.Flatten(source, destination, action, folderPrefix, deleteEmpty);
        }

        if (!int.TryParse(StartBox.Text, out var start)) throw new SafetyException("시작 번호를 숫자로 입력해 주세요.");
        var sort = SortBox.SelectedIndex switch { 0 => "name", 1 => "mtime", _ => "size" };
        var selection = _selection.ToArray();
        var prefix = PrefixBox.Text;
        var suffix = SuffixBox.Text;
        var padding = PaddingBox.SelectedIndex + 1;
        var descending = DescendingBox.IsChecked == true;
        return () => Planner.SequentialRename(selection, prefix, suffix, padding, start, sort, descending);
    }

    private async void Apply_Click(object sender, RoutedEventArgs e)
    {
        if (_plan is null) return;
        var confirm = new ConfirmWindow(_plan) { Owner = this };
        if (confirm.ShowDialog() != true) return;
        SetBusy(true);
        var progress = new Progress<(int Current, int Total, string Name)>(value =>
        {
            StatusText.Text = $"{value.Current:N0}/{value.Total:N0} · {value.Name}";
        });
        try
        {
            var plan = _plan;
            await Task.Run(() => Executor.Execute(plan, progress));
            RefreshExplorer(plan);
            MessageBox.Show(this, $"{plan.Items.Count:N0}개 파일 작업을 완료했습니다.", "FileFlow Lite", MessageBoxButton.OK, MessageBoxImage.Information);
            Close();
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "작업을 완료하지 못했습니다", MessageBoxButton.OK, MessageBoxImage.Error);
            await RefreshPreviewAsync();
        }
        finally { SetBusy(false); }
    }

    private async void Undo_Click(object sender, RoutedEventArgs e)
    {
        if (MessageBox.Show(this, "직전 작업을 안전하게 되돌릴까요?\n파일이 이후 변경된 경우에는 중단됩니다.", "직전 작업 실행 취소", MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes) return;
        SetBusy(true);
        try
        {
            var count = await Task.Run(() => Executor.UndoLatest());
            SHChangeNotify(0x08000000, 0, IntPtr.Zero, IntPtr.Zero);
            MessageBox.Show(this, $"{count:N0}개 파일을 원래 상태로 되돌렸습니다.", "FileFlow Lite", MessageBoxButton.OK, MessageBoxImage.Information);
            Close();
        }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "실행 취소 실패", MessageBoxButton.OK, MessageBoxImage.Error); }
        finally { SetBusy(false); }
    }

    private void ChooseDestination_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFolderDialog { Title = "파일을 모을 대상 폴더 선택", Multiselect = false };
        if (Directory.Exists(DestinationPathBox.Text)) dialog.InitialDirectory = DestinationPathBox.Text;
        else if (Directory.Exists(Path.GetDirectoryName(DestinationPathBox.Text))) dialog.InitialDirectory = Path.GetDirectoryName(DestinationPathBox.Text);
        if (dialog.ShowDialog(this) == true) { DestinationPathBox.Text = dialog.FolderName; _ = RefreshPreviewAsync(); }
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e) => await RefreshPreviewAsync();
    private async void Option_Changed(object sender, RoutedEventArgs e)
    {
        if (TransferModeBox is not null && DeleteEmptyBox is not null)
        {
            DeleteEmptyBox.IsEnabled = TransferModeBox.SelectedIndex == 1;
            if (!DeleteEmptyBox.IsEnabled) DeleteEmptyBox.IsChecked = false;
        }
        await RefreshPreviewAsync();
    }
    private async void Option_Changed(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (TransferModeBox is not null && DeleteEmptyBox is not null)
        {
            DeleteEmptyBox.IsEnabled = TransferModeBox.SelectedIndex == 1;
            if (!DeleteEmptyBox.IsEnabled) DeleteEmptyBox.IsChecked = false;
        }
        await RefreshPreviewAsync();
    }
    private async void Option_Changed(object sender, System.Windows.Controls.TextChangedEventArgs e) => await RefreshPreviewAsync();

    private void SetBusy(bool busy)
    {
        ApplyButton.IsEnabled = !busy && _plan is { Items.Count: > 0 };
        FlattenOptions.IsEnabled = !busy;
        RenameOptions.IsEnabled = !busy;
        IsEnabled = !busy;
    }

    private static string ActionText(FileAction action) => action switch { FileAction.Copy => "복사", FileAction.Move => "이동", _ => "이름 변경" };
    private static string FormatSize(long bytes)
    {
        string[] units = ["B", "KB", "MB", "GB", "TB"];
        var value = (double)bytes; var index = 0;
        while (value >= 1024 && index < units.Length - 1) { value /= 1024; index++; }
        return index == 0 ? $"{bytes:N0} B" : $"{value:0.0} {units[index]}";
    }

    private static void RefreshExplorer(OperationPlan plan)
    {
        SHChangeNotify(0x08000000, 0, IntPtr.Zero, IntPtr.Zero);
    }

    private void ApplyWindowsBackdrop()
    {
        if (!OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22000)) return;
        var hwnd = new WindowInteropHelper(this).Handle;
        var backdrop = 2;
        _ = DwmSetWindowAttribute(hwnd, 38, ref backdrop, sizeof(int));
    }

    private void Cancel_Click(object sender, RoutedEventArgs e) => Close();

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

    [DllImport("shell32.dll")]
    private static extern void SHChangeNotify(uint eventId, uint flags, IntPtr item1, IntPtr item2);
}
