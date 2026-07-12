using System.Windows;
using FileFlow.Core;

namespace FileFlow.Worker;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        try
        {
            if (e.Args.Length == 1 && e.Args[0] == "--undo")
            {
                var answer = MessageBox.Show(
                    "직전 작업을 안전하게 되돌릴까요?\n파일이 이후 변경된 경우에는 아무것도 바꾸지 않고 중단됩니다.",
                    "직전 작업 실행 취소 — FileFlow Lite",
                    MessageBoxButton.YesNo,
                    MessageBoxImage.Question,
                    MessageBoxResult.No);
                if (answer != MessageBoxResult.Yes)
                {
                    Shutdown();
                    return;
                }
                var count = Executor.UndoLatest();
                MessageBox.Show($"{count:N0}개 파일을 원래 상태로 되돌렸습니다.", "FileFlow Lite", MessageBoxButton.OK, MessageBoxImage.Information);
                Shutdown();
                return;
            }
            if (e.Args.Length != 2 || e.Args[0] is not ("--flatten-manifest" or "--rename-manifest"))
                throw new SafetyException("파일 탐색기에서 FileFlow Lite 명령을 실행해 주세요.");
            var files = SelectionManifest.ReadAndDelete(e.Args[1]);
            var mode = e.Args[0] == "--flatten-manifest" ? WorkerMode.Flatten : WorkerMode.Rename;
            var window = new MainWindow(mode, files);
            MainWindow = window;
            window.Show();
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "FileFlow Lite", MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(1);
        }
    }
}
