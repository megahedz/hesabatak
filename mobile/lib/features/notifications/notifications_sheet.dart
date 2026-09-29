import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';

/// تنبيهات عملية حقيقية من السيرفر (Phase 7): أصناف نافدة/منخفضة،
/// عملاء مستحق لنا، موردون مستحق لهم — تُعرض من جرس الرئيسية.
///
/// الرجوع: (kind → أيقونة/لون) مع ترتيب العناصر العاجلة أولًا كما يرسلها
/// السيرفر (error ثم warning ثم info).
Future<void> showNotificationsSheet(BuildContext context) async {
  final api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  await showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
    builder: (sheetCtx) => SafeArea(
      child: Container(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(sheetCtx).size.height * 0.75,
        ),
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const IconTile(
                  icon: Icons.notifications_rounded,
                  background: AppColors.blueTint,
                  color: AppColors.primary,
                  size: 40,
                ),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text('التنبيهات',
                      style: TextStyle(
                          fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.navy)),
                ),
                IconButton(
                  icon: const Icon(Icons.close, color: AppColors.textSecondary),
                  onPressed: () => Navigator.of(sheetCtx).pop(),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Expanded(
              child: FutureBuilder<Map<String, dynamic>>(
                future: api.getNotifications(AppConfig.companyId),
                builder: (context, snapshot) {
                  if (snapshot.connectionState != ConnectionState.done) {
                    return const Center(child: CircularProgressIndicator());
                  }
                  if (snapshot.hasError) {
                    return const Center(
                      child: Text('تعذر تحميل التنبيهات — تأكد من الاتصال.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: AppColors.textSecondary)),
                    );
                  }
                  final alerts =
                      (snapshot.data!['alerts'] as List<dynamic>? ?? const []).cast<Map<String, dynamic>>();
                  if (alerts.isEmpty) {
                    return Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const SizedBox(height: 24),
                        const IconTile(
                          icon: Icons.check_circle_rounded,
                          background: AppColors.greenTint,
                          color: AppColors.greenDark,
                          size: 56,
                        ),
                        const SizedBox(height: 12),
                        const Text('كل شيء تحت السيطرة — لا توجد تنبيهات',
                            style: TextStyle(color: AppColors.textSecondary)),
                        const SizedBox(height: 24),
                      ],
                    );
                  }
                  return ListView(
                    shrinkWrap: true,
                    children: [
                      for (final a in alerts)
                        _AlertCard(
                          kind: a['kind'] as String? ?? 'info',
                          title: a['title'] as String? ?? '',
                          body: a['body'] as String? ?? '',
                        ),
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class _AlertCard extends StatelessWidget {
  const _AlertCard({required this.kind, required this.title, required this.body});
  final String kind;
  final String title;
  final String body;

  (IconData, Color, Color) get _style {
    switch (kind) {
      case 'stock_out':
        return (Icons.warning_rounded, AppColors.redTint, AppColors.red);
      case 'stock_low':
        return (Icons.inventory_2_rounded, AppColors.amberTint, AppColors.amber);
      case 'receivable':
        return (Icons.person_rounded, AppColors.greenTint, AppColors.green);
      case 'payable':
        return (Icons.storefront_rounded, AppColors.blueTint, AppColors.primary);
      default:
        return (Icons.info_rounded, AppColors.greyTint, AppColors.textSecondary);
    }
  }

  @override
  Widget build(BuildContext context) {
    final (icon, bg, fg) = _style;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          IconTile(icon: icon, background: bg, color: fg, size: 42),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(
                        fontSize: 14, fontWeight: FontWeight.w700, color: AppColors.navy)),
                const SizedBox(height: 2),
                Text(body,
                    style: const TextStyle(fontSize: 12.5, color: AppColors.textSecondary)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
