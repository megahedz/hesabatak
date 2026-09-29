import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';

import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../reports/export_service.dart';
import '../theme.dart';

/// صف مرفقات جاهز للإدراج في أي نموذج إدخال (عميل/مورد/بيع/شراء/قبض/دفع):
/// زر «إرفاق صورة أو مستند» + قائمة المرفقات المرفوعة مع فتح/حذف.
///
/// يقبل صورًا ومستندات (خصوصًا PDF) بحد 2.5MB لكل ملف — السيرفر يرفض غير ذلك
/// برسالة عربية واضحة. عند فتح الملف: الصور تُعرض من البايتات، وغيرها
/// (PDF ومستندات) يُشارك عبر شير النظام (حفظ/فتح بأي تطبيق).
class AttachmentField extends StatefulWidget {
  const AttachmentField({
    super.key,
    required this.ownerKind,
    required this.ownerId,
    this.title = 'المرفقات (صورة أو مستند PDF)',
  });

  /// أحد: customer, supplier, sale, purchase, payment.
  final String ownerKind;
  final int ownerId;
  final String title;

  @override
  State<AttachmentField> createState() => _AttachmentFieldState();
}

class _AttachmentFieldState extends State<AttachmentField> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  List<dynamic> _items = [];
  bool _loading = true;
  bool _uploading = false;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      final items = await _api.listAttachments(widget.ownerKind, widget.ownerId);
      if (mounted) setState(() { _items = items; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickAndUpload() async {
    final picked = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['jpg', 'jpeg', 'png', 'webp', 'gif', 'heic', 'pdf'],
      withData: true,
    );
    if (picked == null) return;
    final f = picked.files.single;
    if (f.bytes == null) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('تعذر قراءة الملف — جرّب ملفًا أصغر.')));
      }
      return;
    }
    final ext = (f.extension ?? '').toLowerCase();
    final contentType = ext == 'pdf' ? 'application/pdf' : 'image/$ext';
    setState(() => _uploading = true);
    try {
      await _api.uploadAttachment(
        ownerKind: widget.ownerKind,
        ownerId: widget.ownerId,
        bytes: f.bytes!,
        fileName: f.name,
        contentType: contentType,
      );
      await _reload();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(e.statusCode == 400
                ? 'الملف غير مدعوم أو حجمه أكبر من 2.5 ميغابايت.'
                : 'تعذر رفع الملف. حاول مرة أخرى.')));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('تعذر رفع الملف. تأكد من الاتصال وحاول مرة أخرى.')));
      }
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  Future<void> _open(Map<String, dynamic> att) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      messenger.showSnackBar(const SnackBar(content: Text('جارٍ تجهيز الملف…'), duration: Duration(seconds: 2)));
      final file = await _api.downloadAttachment(
          widget.ownerKind, widget.ownerId, att['id'] as int);
      await shareFile(context, file.bytes, file.fileName);
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('تعذر فتح الملف. حاول مرة أخرى.')));
    }
  }

  Future<void> _delete(Map<String, dynamic> att) async {
    try {
      await _api.deleteAttachment(widget.ownerKind, widget.ownerId, att['id'] as int);
      await _reload();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('تعذر حذف المرفق. حاول مرة أخرى.')));
      }
    }
  }

  String _sizeLabel(int bytes) {
    if (bytes >= 1024 * 1024) return '${(bytes / 1024 / 1024).toStringAsFixed(1)} م.ب';
    return '${(bytes / 1024).round()} ك.ب';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.greyTint,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const Icon(Icons.attach_file, size: 18, color: AppColors.navy),
              const SizedBox(width: 6),
              Expanded(
                child: Text(widget.title,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: AppColors.navy)),
              ),
              _uploading
                  ? const SizedBox(
                      height: 16, width: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : IconButton(
                      tooltip: 'إرفاق ملف',
                      visualDensity: VisualDensity.compact,
                      icon: const Icon(Icons.add_circle, color: AppColors.primary),
                      onPressed: _pickAndUpload,
                    ),
            ],
          ),
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text('…', textAlign: TextAlign.center,
                  style: TextStyle(color: AppColors.textSecondary, fontSize: 12)),
            )
          else if (_items.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 4),
              child: Text('لا توجد مرفقات — أضف صورة فاتورة أو مستند PDF',
                  style: TextStyle(color: AppColors.textSecondary, fontSize: 12)),
            )
          else
            for (final att in _items)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Row(
                  children: [
                    Icon(
                      (att['content_type'] as String) == 'application/pdf'
                          ? Icons.picture_as_pdf_rounded
                          : Icons.image_rounded,
                      size: 20,
                      color: (att['content_type'] as String) == 'application/pdf'
                          ? AppColors.red
                          : AppColors.primary,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: InkWell(
                        onTap: () => _open(att),
                        borderRadius: BorderRadius.circular(8),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(att['file_name'] as String,
                                maxLines: 1, overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.navy)),
                            Text(_sizeLabel(att['size_bytes'] as int),
                                style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
                          ],
                        ),
                      ),
                    ),
                    IconButton(
                      tooltip: 'فتح',
                      visualDensity: VisualDensity.compact,
                      icon: const Icon(Icons.open_in_new, size: 18, color: AppColors.primary),
                      onPressed: () => _open(att),
                    ),
                    IconButton(
                      tooltip: 'حذف',
                      visualDensity: VisualDensity.compact,
                      icon: const Icon(Icons.delete_outline, size: 18, color: AppColors.red),
                      onPressed: () => _delete(att),
                    ),
                  ],
                ),
              ),
        ],
      ),
    );
  }
}
