/// Default no-op implementation — replaced by conditional import when either
/// dart:io or dart:js_interop is available (see share_downloader.dart).
Future<bool> shareBytesImpl(List<int> bytes, String fileName, String text) async {
  return false;
}
