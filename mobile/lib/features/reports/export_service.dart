import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/api_client.dart';
import '../../core/app_config.dart';
import 'share_downloader.dart';

/// Phase 6 (spec §39/§40): download a report as PDF/Excel from the backend
/// and hand it to the platform — Android share sheet on mobile, direct
/// browser download on web. Returns false when the download fails so the
/// caller can show its own Arabic error.
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
    final ok = await shareBytes(file.bytes, file.fileName, 'تقرير حساباتك');
    if (!ok && context.mounted) {
      messenger.showSnackBar(
          const SnackBar(content: Text('تعذر مشاركة الملف. حاول مرة أخرى.')));
    }
    return ok;
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

/// مشاركة ملف عام (يُستخدم لفتح/تنزيل المرفقات والنسخ الاحتياطية) — يعمل على
/// الموبايل (شير النظام) وعلى الويب (تنزيل مباشر).
Future<bool> shareFile(BuildContext context, List<int> bytes, String fileName) async {
  return shareBytes(bytes, fileName, 'ملف من حساباتك');
}

Future<bool> shareBackupFile(BuildContext context, List<int> bytes, String fileName) async {
  return shareBytes(bytes, fileName, 'نسخة احتياطية من حساباتك');
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
