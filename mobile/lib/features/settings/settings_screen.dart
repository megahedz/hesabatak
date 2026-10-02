import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../core/session.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../dashboard/dashboard_screen.dart' show showBackupSheet;
import '../home/home_shell.dart';
import 'team_screen.dart';

/// الإعدادات — بيانات المشروع، إعدادات الضريبة والمخزون والسنة المالية،
/// النسخ الاحتياطي والاستعادة، وتسجيل الخروج — بنفس نظام التصميم.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);

  final _name = TextEditingController();
  final _businessType = TextEditingController();
  final _vatRate = TextEditingController();
  final _taxCard = TextEditingController();
  bool _vatEnabled = false;
  bool _inventoryEnabled = false;
  bool _withholdingEnabled = false;
  int _fiscalStart = 1;

  bool _loading = true;
  bool _failed = false;
  bool _saving = false;

  // Phase 7: دور المستخدم يحدد ماذا يرى ويفعل في هذه الشاشة.
  String _role = 'staff';
  List<String> _permissions = const [];
  bool get _canManageSettings => _permissions.contains('manage_settings');
  bool get _isOwner => _role == 'owner';

  static const _months = <(String, int)>[
    ('يناير', 1), ('فبراير', 2), ('مارس', 3), ('أبريل', 4),
    ('مايو', 5), ('يونيو', 6), ('يوليو', 7), ('أغسطس', 8),
    ('سبتمبر', 9), ('أكتوبر', 10), ('نوفمبر', 11), ('ديسمبر', 12),
  ];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _name.dispose();
    _businessType.dispose();
    _vatRate.dispose();
    _taxCard.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _failed = false;
    });
    try {
      final results = await Future.wait([
        _api.getSettings(AppConfig.companyId),
        _api.getMyMembership(AppConfig.companyId),
      ]);
      final s = results[0] as Map<String, dynamic>;
      final me = results[1] as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        _name.text = s['name'] as String? ?? '';
        _businessType.text = s['business_type'] as String? ?? '';
        _vatEnabled = s['vat_enabled'] == true;
        _vatRate.text = s['vat_rate'] as String? ?? '14';
        _inventoryEnabled = s['inventory_enabled'] == true;
        _withholdingEnabled = s['withholding_enabled'] == true;
        _taxCard.text = s['tax_card_no'] as String? ?? '';
        _fiscalStart = (s['fiscal_year_start_month'] as num?)?.toInt() ?? 1;
        _role = me['role'] as String? ?? 'staff';
        _permissions = (me['permissions'] as List<dynamic>? ?? const [])
            .map((e) => e.toString())
            .toList();
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _failed = true;
      });
    }
  }

  Future<void> _save() async {
    final rate = double.tryParse(_vatRate.text.trim());
    if (rate == null || rate < 0 || rate > 100) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('نسبة الضريبة يجب أن تكون بين 0 و 100')));
      return;
    }
    setState(() => _saving = true);
    try {
      await _api.updateSettings(
        AppConfig.companyId,
        name: _name.text,
        businessType: _businessType.text.trim().isEmpty ? null : _businessType.text.trim(),
        vatEnabled: _vatEnabled,
        vatRate: rate,
        inventoryEnabled: _inventoryEnabled,
        fiscalYearStartMonth: _fiscalStart,
        taxCardNo: _taxCard.text.trim(),
        withholdingEnabled: _withholdingEnabled,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('تم حفظ الإعدادات')));
      _load();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('تعذر حفظ الإعدادات. حاول مرة أخرى.')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = AppSession.instance;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(title: 'الإعدادات'),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _failed
              ? _ErrorState(onRetry: _load)
              : RefreshIndicator(
                  color: AppColors.primary,
                  onRefresh: () async => _load(),
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      // ===== بيانات المشروع =====
                      SectionCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Row(
                              children: [
                                IconTile(
                                  icon: Icons.store_mall_directory_rounded,
                                  background: AppColors.blueTint,
                                  color: AppColors.primary,
                                  size: 40,
                                ),
                                SizedBox(width: 10),
                                Text('بيانات المشروع',
                                    style: TextStyle(
                                        fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.navy)),
                              ],
                            ),
                            const SizedBox(height: 14),
                            TextField(
                              controller: _name,
                              decoration: const InputDecoration(
                                  labelText: 'اسم المشروع', prefixIcon: Icon(Icons.badge_outlined, size: 20)),
                            ),
                            const SizedBox(height: 12),
                            TextField(
                              controller: _businessType,
                              decoration: const InputDecoration(
                                  labelText: 'نشاط المشروع', prefixIcon: Icon(Icons.category_outlined, size: 20)),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),

                      // ===== فريق العمل (الإدارة للمالك فقط) =====
                      SectionCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            ListTile(
                              contentPadding: EdgeInsets.zero,
                              leading: const IconTile(
                                icon: Icons.groups_rounded,
                                background: AppColors.greenTint,
                                color: AppColors.greenDark,
                                size: 42,
                              ),
                              title: const Text('فريق العمل',
                                  style: TextStyle(
                                      fontSize: 14.5, fontWeight: FontWeight.w700, color: AppColors.navy)),
                              subtitle: Text(
                                _isOwner
                                    ? 'أضف محاسبًا أو موظفًا وحدد صلاحياته'
                                    : 'عرض أعضاء المشروع وأدوارهم',
                                style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                              ),
                              trailing: const Icon(Icons.chevron_left, color: AppColors.textSecondary),
                              onTap: () => Navigator.of(context)
                                  .push(MaterialPageRoute(builder: (_) => const TeamScreen())),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),

                      // ===== الضريبة والمخزون (التعديل للمالك فقط) =====
                      SectionCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Row(
                              children: [
                                IconTile(
                                  icon: Icons.receipt_long_rounded,
                                  background: AppColors.tealTint,
                                  color: AppColors.teal,
                                  size: 40,
                                ),
                                SizedBox(width: 10),
                                Text('الضريبة والمخزون',
                                    style: TextStyle(
                                        fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.navy)),
                              ],
                            ),
                            if (!_canManageSettings) ...[
                              const SizedBox(height: 8),
                              const Text(
                                'عرض فقط — تعديل الإعدادات من صلاحيات مالك المشروع.',
                                style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                              ),
                            ],
                            const SizedBox(height: 14),
                            SwitchListTile(
                              value: _vatEnabled,
                              onChanged: _canManageSettings ? (v) => setState(() => _vatEnabled = v) : null,
                              contentPadding: EdgeInsets.zero,
                              title: const Text('تفعيل ضريبة القيمة المضافة',
                                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                              subtitle: const Text('تُحسب تلقائيًا على الفواتير',
                                  style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                            ),
                            if (_vatEnabled) ...[
                              TextField(
                                controller: _vatRate,
                                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                decoration: const InputDecoration(
                                    labelText: 'نسبة الضريبة %', suffixText: '%'),
                              ),
                              const SizedBox(height: 12),
                            ],
                            SwitchListTile(
                              value: _withholdingEnabled,
                              onChanged: _canManageSettings ? (v) => setState(() => _withholdingEnabled = v) : null,
                              contentPadding: EdgeInsets.zero,
                              title: const Text('تفعيل ضريبة الخصم',
                                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                              subtitle: const Text('1% توريدات — 3% خدمات — 5% استشارات (قانون 91 لسنة 2005)',
                                  style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                            ),
                            if (_withholdingEnabled) ...[
                              TextField(
                                controller: _taxCard,
                                keyboardType: TextInputType.number,
                                decoration: const InputDecoration(
                                    labelText: 'البطاقة الضريبية',
                                    hintText: 'الرقم الذي يظهر في إشعار الخصم',
                                    prefixIcon: Icon(Icons.credit_card, size: 20)),
                              ),
                              const SizedBox(height: 12),
                            ],
                            const SizedBox(height: 4),
                            const Text('بداية السنة المالية',
                                style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                            const SizedBox(height: 6),
                            DropdownButtonFormField<int>(
                              value: _fiscalStart,
                              isDense: true,
                              items: _months
                                  .map((m) => DropdownMenuItem<int>(value: m.$2, child: Text(m.$1)))
                                  .toList(),
                              onChanged: (v) => setState(() => _fiscalStart = v ?? 1),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),

                      // ===== حفظ =====
                      if (!_canManageSettings)
                        const SizedBox.shrink()
                      else
                        FilledButton.icon(
                        onPressed: _saving ? null : _save,
                        icon: _saving
                            ? const SizedBox(
                                height: 18, width: 18,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                            : const Icon(Icons.save_outlined, size: 20),
                        label: const Text('حفظ الإعدادات'),
                      ),
                      const SizedBox(height: 14),

                      // ===== النسخ الاحتياطي =====
                      SectionCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const Row(
                              children: [
                                IconTile(
                                  icon: Icons.backup_rounded,
                                  background: AppColors.purpleTint,
                                  color: AppColors.purple,
                                  size: 40,
                                ),
                                SizedBox(width: 10),
                                Expanded(
                                  child: Text('النسخ الاحتياطي والاستعادة',
                                      style: TextStyle(
                                          fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.navy)),
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            const Text(
                              'خذ نسخة كاملة من بيانات مشروعك في ملف واحد، أو استعد نسخة سابقة.',
                              style: TextStyle(fontSize: 12.5, color: AppColors.textSecondary),
                            ),
                            const SizedBox(height: 12),
                            OutlinedButton.icon(
                              onPressed: () => showBackupSheet(context),
                              icon: const Icon(Icons.backup_outlined, size: 20),
                              label: const Text('إدارة النسخة الاحتياطية'),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),

                      // ===== الحساب =====
                      SectionCard(
                        child: ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const CircleAvatar(
                            backgroundColor: AppColors.blueTint,
                            child: Icon(Icons.person, color: AppColors.primary),
                          ),
                          title: Text(session.userName ?? 'مستخدم',
                              style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.navy)),
                          subtitle: Text(
                            session.userEmail != null && session.userEmail!.isNotEmpty
                                ? session.userEmail!
                                : (session.companyName ?? ''),
                            style: const TextStyle(fontSize: 12),
                          ),
                          trailing: Text('إصدار ${AppConfig.appVersion}',
                              style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
                        ),
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: () => AppSession.instance.logout(),
                        icon: const Icon(Icons.logout, size: 20),
                        label: const Text('تسجيل الخروج'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.red,
                          side: const BorderSide(color: AppColors.red),
                        ),
                      ),
                    ],
                  ),
                ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.onRetry});
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('تعذر تحميل الإعدادات. تأكد من الاتصال وحاول مرة أخرى.',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.textSecondary)),
          const SizedBox(height: 12),
          FilledButton(onPressed: onRetry, child: const Text('إعادة المحاولة')),
        ],
      ),
    );
  }
}
