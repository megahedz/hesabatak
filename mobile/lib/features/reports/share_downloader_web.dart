import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

/// Browser: direct download via Blob + object-URL anchor click (no share
/// sheet exists on the web).
Future<bool> shareBytesImpl(List<int> bytes, String fileName, String text) async {
  try {
    final data = Uint8List.fromList(bytes);
    final blob = web.Blob([data.toJS].toJS);
    final url = web.URL.createObjectURL(blob);
    final anchor = web.HTMLAnchorElement()
      ..href = url
      ..download = fileName;
    anchor.click();
    web.URL.revokeObjectURL(url);
    return true;
  } catch (_) {
    return false;
  }
}
