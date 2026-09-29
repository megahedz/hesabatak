import 'dart:io' as io show File;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/api_client.dart';
import '../../core/app_config.dart';

/// Phase 6 (spec §39/§40): download a report as PDF/Excel from the backend
/// and hand it to the Android share sheet (WhatsApp, email, drive, "save to
/// Files"...). Returns false when the download fails so the caller can show
/// its own Arabic error.
Future<bool> shareReportExport(BuildContext context, String reportKey) async {
  final messenger = ScaffoldMessenger.of(context);
  final format = await _pickFormat(context);
  if (format == null || !context.mounted) return false;

  messenger.showSnackBar(
    const SnackBar(content: Text('جارٍ تجهيز الملف…'), duration: Duration(seconds: 2)),
  );
  try {
    final api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
    final file = await api.downloadExport(reportKey: reportKey, fmt: format);
    if (kIsWeb) {
      // المتصفح: تنزيل مباشر بدون شير النظام (لا ملفات مؤقتة هناك).
      await SharePlus.instance.share(
        ShareParams(files: [XFile.fromData(file.bytes, name: file.fileName)],
            text: 'تقرير حساباتك'),
      );
      return true;
    }
    final path = await _writeTemp(file.bytes, file.fileName);
    await SharePlus.instance.share(
      ShareParams(files: [XFile(path)], text: 'تقرير حساباتك'),
    );
    return true;
  } on ApiException catch (e) {
    messenger.showSnackBar(SnackBar(
      content: Text(e.statusCode == 400
          ? 'تعذر تجهيز التقرير للتصدير.'
          : 'تعذر تصدير التقرير. حاول مرة أخرى.'),
    ));
    return false;
  } catch (_) {
    messenger.showSnackBar(
        const SnackBar(content: Text('تعذر تصدير التقرير. تأكد من الاتصال وحاول مرة أخرى.')));
    return false;
  }
}

/// مشاركة ملف عام (يُستخدم لفتح/تنزيل المرفقات وكشوف الحساب). يستخدم نفس
/// مسار الكتابة المؤقتة + شير النظام.
Future<bool> shareFile(BuildContext context, List<int> bytes, String fileName) async {
  if (kIsWeb) {
    // المتصفح: تنزيل مباشر عبر Blob (share sheet غير موجود على الويب).
    return _shareOnWeb(bytes, fileName);
  }
  return shareBackupFile(context, bytes, fileName);
}

Future<bool> shareBackupFile(BuildContext context, List<int> bytes, String fileName) async {
  if (kIsWeb) {
    return _shareOnWeb(bytes, fileName);
  }
  final messenger = ScaffoldMessenger.of(context);
  try {
    final path = await _writeTemp(bytes, fileName);
    await SharePlus.instance.share(
      ShareParams(files: [XFile(path)], text: 'نسخة احتياطية من حساباتك'),
    );
    return true;
  } catch (_) {
    messenger.showSnackBar(
        const SnackBar(content: Text('تعذر مشاركة الملف. حاول مرة أخرى.')));
    return false;
  }
}

/// تنزيل الملف مباشرة في المتصفح عبر Blob + رابط مؤقت (يُستخدم على الويب فقط).
Future<bool> _shareOnWeb(List<int> bytes, String fileName) async {
  try {
    final blob = web.Blob([bytes.toJS].toJS);
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

Future<String> _writeTemp(List<int> bytes, String fileName) async {
  if (kIsWeb) {
    // المتصفح: يكفي اسم الملف — مشاركة الملف نفسه تتم عبر XFile.fromData.
    return fileName;
  }
  final dir = await getTemporaryDirectory();
  final file = io.File('${dir.path}/$fileName');
  await file.writeAsBytes(bytes, flush: true);
  return file.path;
}

Future<String?> _pickFormat(BuildContext context) async {
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('صيغة التصدير'),
      content: const Text('اختر الصيغة المناسبة لتصدير التقرير'),
      actions: [
        TextButton.icon(
          onPressed: () => Navigator.of(ctx).pop('pdf'),
          icon: const Icon(Icons.picture_as_pdf_outlined),
          label: const Text('PDF'),
        ),
        FilledButton.icon(
          onPressed: () => Navigator.of(ctx).pop('excel'),
          icon: const Icon(Icons.grid_on_outlined),
          label: const Text('Excel'),
        ),
      ],
    ),
  );
}
