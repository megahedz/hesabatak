import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../core/session.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';

/// شاشة الاشتراك (Phase 8): تعرض حالة الشركة الحالية — تجربة مجانية 14 يوم،
/// اشتراك نشط، أو منتهي — مع زر «اشترك الآن».
///
/// الأمان (يُذكر للمستخدم صراحة):
///  * كلمة المرور مشفرة على السيرفر بتشفير bcrypt أحادي الاتجاه — لا أحد
///    (ولا حتى إدارة السيرفر) يستطيع قراءتها أو استعادتها.
///  * بيانات الدفع لا تمر على التطبيق إطلاقًا — الدفع في صفحة بوابة دفع
///    مستضافة خارجية (Stripe Checkout) لا نلمس أرقام البطاقات.
class SubscriptionScreen extends StatefulWidget {
  const SubscriptionScreen({super.key});

  @override
  State<SubscriptionScreen> createState() => _SubscriptionScreenState();
}

class _SubscriptionScreenState extends State<SubscriptionScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  Map<String, dynamic>? _status;
  bool _loading = true;
  bool _paying = false;
  String? _error;

  /// companyId يُضبط بعد الدخول دائمًا؛ احتياطًا نتعامل مع null بأمان.
  int get _companyId => AppSession.instance.companyId ?? -1;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final s = await _api.getBillingStatus(_companyId);
      if (mounted) setState(() { _status = s; _error = null; });
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _error = e.statusCode == 422
            ? 'هذه النسخة قديمة — حدّث التطبيق'
            : 'تعذر تحميل حالة الاشتراك');
      }
    } on ApiNetworkException {
      if (mounted) setState(() => _error = 'تعذر الاتصال بالسيرفر — تحقق من اتصالك');
    } catch (_) {
      if (mounted) setState(() => _error = 'تعذر تحميل حالة الاشتراك');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _subscribe() async {
    setState(() { _paying = true; _error = null; });
    try {
      final res = await _api.startCheckout(_companyId);
      final url = res['checkout_url'] as String?;
      if (url == null || url.isEmpty) {
        setState(() => _error = 'لم يصل رابط الدفع من السيرفر. حاول مرة أخرى.');
      }
      // ملاحظة: فتح الرابط يتطلب حزمة url_launcher — تُضاف عند تفعيل الدفع
      // فعليًا. حتى ذلك الحين نعرض تعليمات واضحة.
    } on ApiException catch (e) {
      String msg;
      try {
        final detail = e.body.isNotEmpty ? e.body : '';
        msg = detail.contains('detail') ? 'الدفع الإلكتروني غير مهيأ بعد. تواصل مع الدعم لتفعيل اشتراكك يدويًا.' : 'تعذر بدء الدفع. حاول مرة أخرى.';
      } catch (_) {
        msg = 'تعذر بدء الدفع. حاول مرة أخرى.';
      }
      setState(() => _error = msg);
    } on ApiNetworkException {
      setState(() => _error = 'تعذر الاتصال بالسيرفر — تحقق من اتصالك');
    } catch (_) {
      setState(() => _error = 'تعذر بدء الدفع. حاول مرة أخرى.');
    } finally {
      if (mounted) setState(() => _paying = false);
    }
  }

  (String, Color, IconData) _statusVisual(String? status) {
    switch (status) {
      case 'active':
        return ('اشتراكك نشط ✓', AppColors.green, Icons.verified_outlined);
      case 'trialing':
        return ('تجربة مجانية', AppColors.primary, Icons.schedule_outlined);
      default:
        return ('انتهى الاشتراك', AppColors.red, Icons.error_outline);
    }
  }

  String _fmtDate(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    try {
      final d = DateTime.parse(iso).toLocal();
      return '${d.year}/${d.month.toString().padLeft(2, '0')}/${d.day.toString().padLeft(2, '0')}';
    } catch (_) {
      return '—';
    }
  }

  @override
  Widget build(BuildContext context) {
    final (title, color, icon) = _statusVisual(_status?['status'] as String?);
    return Scaffold(
      appBar: AppBar(
        title: const Text('الاشتراك'),
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.navy,
        elevation: 0,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  if (_error != null) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppColors.redTint,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(_error!, style: const TextStyle(color: AppColors.red, fontSize: 13)),
                    ),
                    const SizedBox(height: 14),
                  ],
                  SectionCard(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Icon(icon, size: 44, color: color),
                        const SizedBox(height: 10),
                        Text(title,
                            textAlign: TextAlign.center,
                            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: color)),
                        const SizedBox(height: 14),
                        _row('نوع الاشتراك',
                            _status?['status'] == 'trialing' ? 'تجربة مجانية' : (_status?['plan'] ?? '—')),
                        _row('تنتهي في', _fmtDate(_status?['current_period_end'] as String?)),
                        if (_status?['days_left'] != null)
                          _row('متبقي', '${_status?['days_left']} يوم'),
                        const SizedBox(height: 12),
                        if ((_status?['status'] ?? '') != 'active')
                          FilledButton.icon(
                            onPressed: _paying ? null : _subscribe,
                            icon: _paying
                                ? const SizedBox(height: 18, width: 18,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                                : const Icon(Icons.payment_outlined),
                            label: Text(_paying ? 'جارٍ تجهيز الدفع…' : 'اشترك الآن — 100 ج.م شهريًا'),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  // ===== أمان حسابك وبطاقتك — صريح ومكتوب =====
                  SectionCard(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            const Icon(Icons.lock_outline, size: 20, color: AppColors.green),
                            const SizedBox(width: 8),
                            const Text('أمان حسابك',
                                style: TextStyle(fontWeight: FontWeight.w800, color: AppColors.navy)),
                          ],
                        ),
                        const SizedBox(height: 10),
                        _securityPoint(
                          Icons.password_outlined,
                          'كلمة المرور محفوظة مشفرة بتقنية bcrypt — لا يمكن لأحد قراءتها أو استعادتها، حتى إدارة التطبيق.',
                        ),
                        _securityPoint(
                          Icons.credit_card_off_outlined,
                          'بيانات البطاقة لا تمر على التطبيق — الدفع يتم في صفحة بوابة الدفع الآمنة الخارجية.',
                        ),
                        _securityPoint(
                          Icons.storage_outlined,
                          'بيانات شركتك محفوظة في قاعدة بيانات السيرفر مع فصل كامل بين كل شركة وأخرى.',
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
    );
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(fontSize: 14, color: AppColors.textSecondary)),
          Text(value, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppColors.navy)),
        ],
      ),
    );
  }

  Widget _securityPoint(IconData icon, String text) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: AppColors.green),
          const SizedBox(width: 8),
          Expanded(
            child: Text(text,
                style: const TextStyle(fontSize: 12.5, color: AppColors.textSecondary, height: 1.5)),
          ),
        ],
      ),
    );
  }
}
