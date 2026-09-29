import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

/// Android/iOS/desktop: write to the temp dir and open the system share sheet.
Future<bool> shareBytesImpl(List<int> bytes, String fileName, String text) async {
  try {
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/$fileName');
    await file.writeAsBytes(bytes, flush: true);
    await SharePlus.instance.share(
      ShareParams(files: [XFile(file.path)], text: text),
    );
    return true;
  } catch (_) {
    return false;
  }
}
