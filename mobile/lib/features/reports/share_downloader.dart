/// Shared file-download abstraction that compiles on every platform.
///
/// dart:io and package:web cannot both be imported unconditionally (the web
/// package's js_interop libraries don't exist on the VM/Android target), so
/// each platform gets its own implementation via conditional imports:
///
///   * stub (no-op, replaced below by kIsWeb-guarded callers)
///   * io    — Android/iOS/desktop: write to the temp dir, share via system sheet
///   * web   — browser: Blob + object-URL anchor click (direct download)
import 'share_downloader_stub.dart'
    if (dart.library.io) 'share_downloader_io.dart'
    if (dart.library.js_interop) 'share_downloader_web.dart';

export 'share_downloader_stub.dart' show shareBytes;

/// Hand the bytes to the platform: Android share sheet, browser download, …
Future<bool> shareBytes(List<int> bytes, String fileName, String text) =>
    shareBytesImpl(bytes, fileName, text);
