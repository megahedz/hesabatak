import 'dart:convert';

import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../core/session.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';

/// شاشة الدخول — نفس لغة التصميم المرجعي: خلفية فاتحة بلمسات زرقاء ناعمة،
/// شعار حساباتك في الأعلى، ثم بطاقة بيضاء بها الحقول وزر أزرق «تسجيل الدخول».
/// تتعامل مع الدخول وإنشاء الحساب الأول معًا (spec §56/§57).
///
/// ملاحظات ثبات الواجهة:
///  * عرض المحتوى محدود بـ 480 لوجيكًا حتى لا تتمدد البطاقة على الأجهزة
///    العريضة/التابلت، وكل الأبناء stretch حتى لا يعتمد التخطيط على عرض النص.
///  * التسميات قصيرة، وقواعد كلمة المرور في helperText حتى لا تفيض الحقول.
///  * أسفل الشاشة يظهر رقم الإصدار دائمًا — أسهل طريقة للتأكد أن الجهاز
///    يعمل على آخر APK.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _phoneController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isRegisterMode = false;
  bool _rememberMe = true;
  bool _loading = false;
  bool _obscure = true;
  String? _error;
  bool _isNetworkError = false;

  /// بعد 12 ثانية من الانتظار نعرض رسالة «السيرفر يستيقظ» حتى لا يظن المستخدم
  /// أن التطبيق تعلّق (الخطة المجانية على Render تستيقظ حتى ~45 ثانية).
  bool _wakingServer = false;
  late final Stopwatch _sw = Stopwatch()..start();

  void _checkWaking() {
    if (_loading && !_wakingServer && _sw.elapsedMilliseconds > 12000) {
      if (mounted) setState(() => _wakingServer = true);
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  /// تحقق محلي من صيغة البريد — نفس القاعدة المطبقة على السيرفر.
  static final RegExp _emailRe = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

  /// مؤشر قوة كلمة المرور (0..3): طول 8+ وحرف ورقم.
  int get _passwordStrength {
    final p = _passwordController.text;
    if (p.isEmpty) return 0;
    var score = 0;
    if (p.length >= 8) score++;
    if (p.contains(RegExp(r'[A-Za-z]'))) score++;
    if (p.contains(RegExp(r'\d'))) score++;
    return score;
  }

  /// رسالة عربية مفهومة من رد الخطأ القادم من السيرفر ({"detail": "..."}) —
  /// أخطاء التسجيل (بريد مكرر/غير صالح، كلمة مرور ضعيفة) قابلة للإصلاح من
  /// المستخدم فنعرضها كما هي، وغير ذلك نعرض رسالة عامة.
  String _friendlyRegisterError(ApiException e) {
    if (e.statusCode == 422) {
      return 'هذه النسخة من التطبيق قديمة.\nحدّث التطبيق إلى آخر إصدار ثم أعد المحاولة.';
    }
    try {
      final detail = (jsonDecode(e.body) as Map<String, dynamic>)['detail'];
      if (detail is String && detail.isNotEmpty) return detail;
    } catch (_) {}
    return 'تعذر إنشاء الحساب. تأكد من البيانات وحاول مرة أخرى.';
  }

  Future<void> _submit() async {
    if (_loading) return; // حماية من الضغط المزدوج
    final phone = _phoneController.text.trim();
    final password = _passwordController.text;
    final email = _emailController.text.trim();

    // تحقق محلي قبل أي طلب شبكة — رسائل فورية وواضحة.
    if (_isRegisterMode && _nameController.text.trim().isEmpty) {
      setState(() => _error = 'من فضلك أكمل كل البيانات المطلوبة');
      return;
    }
    if (_isRegisterMode && !_emailRe.hasMatch(email)) {
      setState(() => _error = 'من فضلك أدخل بريدًا إلكترونيًا صحيحًا\nمثال: name@example.com');
      return;
    }
    if (_isRegisterMode &&
        (password.length < 8 || !password.contains(RegExp(r'[A-Za-z]')) || !password.contains(RegExp(r'\d')))) {
      setState(() => _error = 'كلمة المرور يجب أن تكون 8 أحرف على الأقل\nوتحتوي على حرف ورقم واحد على الأقل');
      return;
    }
    if (phone.isEmpty || password.isEmpty) {
      setState(() => _error = 'من فضلك أكمل كل البيانات المطلوبة');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
      _isNetworkError = false;
      _wakingServer = false;
      _sw.reset();
    });
    // مؤقّت خفيف: بعد 12 ثانية من الانتظار نعرض رسالة استيقاظ السيرفر.
    Future.delayed(const Duration(seconds: 12), () => _checkWaking());
    try {
      final result = _isRegisterMode
          ? await _api.registerLong(
              fullName: _nameController.text.trim(), phone: phone, email: email, password: password)
          : await _api.login(phone: phone, password: password);

      AppSession.instance.setAuth(
        token: result['access_token'] as String,
        userName: _isRegisterMode ? _nameController.text.trim() : phone,
        userEmail: _isRegisterMode ? email : null,
      );

      await _resolveActiveCompany();
    } on ApiException catch (e) {
      setState(() {
        if (_isRegisterMode) {
          _error = _friendlyRegisterError(e);
        } else if (e.statusCode == 401) {
          _error = 'رقم الهاتف أو كلمة المرور غير صحيحة';
        } else {
          _error = 'تعذر تسجيل الدخول. حاول مرة أخرى.';
        }
      });
    } on ApiNetworkException {
      // spec §49: never show raw socket/DNS details to the user. errno = 7
      // ("No address associated with hostname") means the phone's network
      // couldn't resolve the server's name — usually a mobile-network DNS
      // hiccup, Private DNS, or a VPN/ad-blocker app. Point the user at the
      // practical fixes instead of the exception text.
      setState(() {
        _isNetworkError = true;
        _error = 'تعذر الاتصال بالسيرفر.\n'
            'تأكد من اتصالك بالإنترنت وحاول مرة أخرى.\n'
            'إن استمرت المشكلة، جرّب شبكة أخرى أو أوقف أي تطبيق VPN/حاجب إعلانات،'
            ' واضبط «Private DNS» في إعدادات الشبكة على auto.';
      });
    } catch (e) {
      setState(() => _error = _isRegisterMode
          ? 'تعذر إنشاء الحساب. جرّب مرة أخرى.'
          : 'تعذر تسجيل الدخول. حاول مرة أخرى.');
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _wakingServer = false;
        });
      }
    }
  }

  /// After login: use the user's first company if they have one, otherwise
  /// prompt them to create their first company right here (spec §56/§57's
  /// onboarding — "ابدأ الآن" → إنشاء الشركة — folded into the login flow
  /// so a brand-new user doesn't hit a dead end after registering).
  Future<void> _resolveActiveCompany() async {
    try {
      final companies = await _api.listMyCompanies();
      if (companies.isNotEmpty) {
        final first = companies.first as Map<String, dynamic>;
        AppSession.instance.setActiveCompany(id: first['id'] as int, name: first['name'] as String);
        return;
      }
      if (!mounted) return;
      final companyName = await _promptForCompanyName();
      if (companyName == null || companyName.isEmpty) return;
      final created = await _api.createCompany(name: companyName);
      AppSession.instance.setActiveCompany(id: created['id'] as int, name: created['name'] as String);
    } on ApiNetworkException {
      if (mounted) {
        setState(() => _error = 'تعذر الاتصال بالسيرفر. تأكد من اتصالك بالإنترنت وحاول مرة أخرى.');
      }
    } catch (e) {
      if (mounted) {
        setState(() => _error = 'تعذر تجهيز الشركة. حاول مرة أخرى.');
      }
    }
  }

  Future<String?> _promptForCompanyName() {
    final controller = TextEditingController();
    return showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => Directionality(
        textDirection: TextDirection.rtl,
        child: AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Text('أهلاً بك في حساباتك'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('تابع شغلك واعرف مكسبك بسهولة. ابدأ بإدخال اسم مشروعك:'),
              const SizedBox(height: 12),
              TextField(
                controller: controller,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'اسم المشروع أو المحل'),
              ),
            ],
          ),
          actions: [
            FilledButton(onPressed: () => Navigator.of(ctx).pop(controller.text.trim()), child: const Text('ابدأ الآن')),
          ],
        ),
      ),
    );
  }

  /// الدخول بجوجل: الربط مع السيرفر (OAuth) لم يكتمل بعد — نوضح للمستخدم
  /// ماذا سيتاح قريبًا بدل زر صامت لا يفعل شيئًا.
  void _showGooglePendingInfo() {
    showDialog<void>(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: TextDirection.rtl,
        child: AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Text('الدخول بحساب Google'),
          content: const Text(
            'تسجيل الدخول بجوجل قيد التهيئة على السيرفر وسيصاح قريبًا.\n\n'
            'حتى ذلك الحين: سجّل ببريدك ورقم هاتفك وكلمة مرور — كلمة المرور محفوظة مشفرة (bcrypt) ولا يستطيع أحد قراءتها.',
          ),
          actions: [TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('حسنًا'))],
        ),
      ),
    );
  }

  /// «نسيت كلمة المرور؟» — لا يوجد بعد endpoint لاستعادة كلمة المرور، فنشرح
  /// ذلك بصراحة بدل الزر المضلل الذي كان يبدّل لوضع التسجيل فقط.
  void _showForgotPasswordDialog() {
    showDialog<void>(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: TextDirection.rtl,
        child: AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Text('استعادة كلمة المرور'),
          content: const Text(
            'استعادة كلمة المرور تلقائيًا غير متاحة بعد.\n\n'
            'تواصل مع مالك المشروع لإعادة تعيينها، أو أنشئ حسابًا جديدًا برقم هاتف مختلف.',
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('حسنًا')),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFEDF4FC), AppColors.background],
          ),
        ),
        child: SafeArea(
          child: Center(
            // ConstraintBox يمنع تمدد البطاقة على الشاشات العريضة، و
            // SingleChildScrollView يسمح بالتمرير عند فتح لوحة المفاتيح.
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 480),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Center(child: HesabatakLogo(size: 96)),
                    const SizedBox(height: 12),
                    const Text('حساباتك',
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: AppColors.navy)),
                    const SizedBox(height: 4),
                    const Text('إدارة أعمالك بسهولة',
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 14, color: AppColors.textSecondary)),
                    const SizedBox(height: 6),
                    // طمأنة صريحة: كلمة المرور مشفرة دائمًا على السيرفر.
                    const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.lock_outline, size: 13, color: AppColors.greenDark),
                        SizedBox(width: 4),
                        Text('كلمة المرور محفوظة مشفرة (bcrypt)',
                            style: TextStyle(fontSize: 11.5, color: AppColors.textSecondary)),
                      ],
                    ),
                    const SizedBox(height: 22),
                    SectionCard(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          if (_isRegisterMode) ...[
                            TextField(
                              controller: _nameController,
                              textInputAction: TextInputAction.next,
                              decoration: const InputDecoration(
                                labelText: 'الاسم',
                                prefixIcon: Icon(Icons.person_outline),
                              ),
                            ),
                            const SizedBox(height: 14),
                            TextField(
                              controller: _emailController,
                              keyboardType: TextInputType.emailAddress,
                              autocorrect: false,
                              textInputAction: TextInputAction.next,
                              decoration: const InputDecoration(
                                labelText: 'البريد الإلكتروني',
                                hintText: 'name@example.com',
                                prefixIcon: Icon(Icons.alternate_email),
                              ),
                            ),
                            const SizedBox(height: 14),
                          ],
                          TextField(
                            controller: _phoneController,
                            keyboardType: TextInputType.phone,
                            textInputAction: TextInputAction.next,
                            decoration: const InputDecoration(
                              labelText: 'رقم الهاتف',
                              prefixIcon: Icon(Icons.person_outline),
                            ),
                          ),
                          const SizedBox(height: 14),
                          TextField(
                            controller: _passwordController,
                            obscureText: _obscure,
                            onChanged: (_) => setState(() {}),
                            decoration: InputDecoration(
                              labelText: 'كلمة المرور',
                              helperText: _isRegisterMode ? '8 أحرف على الأقل مع رقم' : null,
                              prefixIcon: const Icon(Icons.lock_outline),
                              suffixIcon: IconButton(
                                icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                                onPressed: () => setState(() => _obscure = !_obscure),
                              ),
                            ),
                          ),
                          if (_isRegisterMode && _passwordController.text.isNotEmpty) ...[
                            const SizedBox(height: 8),
                            Row(
                              children: [
                                for (var i = 0; i < 3; i++)
                                  Expanded(
                                    child: Container(
                                      height: 4,
                                      margin: EdgeInsetsDirectional.only(end: i == 2 ? 0 : 6),
                                      decoration: BoxDecoration(
                                        color: i < _passwordStrength
                                            ? (_passwordStrength == 1
                                                ? AppColors.red
                                                : _passwordStrength == 2
                                                    ? AppColors.amber
                                                    : AppColors.greenDark)
                                            : AppColors.greyTint,
                                        borderRadius: BorderRadius.circular(2),
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              _passwordStrength < 2 ? 'كلمة مرور ضعيفة' : 'كلمة مرور جيدة',
                              style: TextStyle(
                                fontSize: 11,
                                color: _passwordStrength < 2 ? AppColors.red : AppColors.greenDark,
                              ),
                            ),
                          ],
                          if (_error != null) ...[
                            const SizedBox(height: 12),
                            SelectableText(_error!,
                                style: const TextStyle(color: AppColors.red, fontSize: 13),
                                textAlign: TextAlign.center),
                          ],
                          const SizedBox(height: 8),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Row(
                                children: [
                                  SizedBox(
                                    height: 22,
                                    width: 22,
                                    child: Checkbox(
                                      value: _rememberMe,
                                      activeColor: AppColors.primary,
                                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                                      onChanged: _loading ? null : (v) => setState(() => _rememberMe = v ?? true),
                                    ),
                                  ),
                                  const SizedBox(width: 6),
                                  const Text('تذكّني', style: TextStyle(fontSize: 13.5, color: AppColors.navy)),
                                ],
                              ),
                              TextButton(
                                onPressed: _loading
                                    ? null
                                    : () {
                                        if (_isRegisterMode) {
                                          setState(() => _isRegisterMode = false);
                                        } else {
                                          _showForgotPasswordDialog();
                                        }
                                      },
                                child: Text(
                                  _isRegisterMode ? 'لديك حساب؟ سجّل الدخول' : 'نسيت كلمة المرور؟',
                                  style: const TextStyle(fontSize: 13, color: AppColors.primary),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          // السيرفر على الخطة المجانية قد يكون نائمًا؛ أول عملية
                          // تسجيل بعد فترة خمول قد تستغرق حتى دقيقة — نوضح ذلك
                          // للمستخدم حتى لا يظن أن الزر معلّق.
                          if (_isRegisterMode && !_loading) ...[
                            Text(
                              'ملاحظة: أول تسجيل بعد فترة راحة قد يستغرق حتى دقيقة.',
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: 11.5, color: AppColors.textSecondary.withOpacity(0.9)),
                            ),
                            const SizedBox(height: 6),
                          ],
                          FilledButton(
                            onPressed: _loading ? null : _submit,
                            child: _loading
                                ? Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      const SizedBox(
                                          height: 18,
                                          width: 18,
                                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)),
                                      const SizedBox(width: 10),
                                      Flexible(
                                        child: Text(
                                            _wakingServer
                                                ? 'السيرفر يستيقظ — لحظات ويتم الدخول…'
                                                : _isRegisterMode
                                                    ? 'جارٍ إنشاء الحساب…'
                                                    : 'جارٍ تسجيل الدخول…',
                                            overflow: TextOverflow.ellipsis),
                                      ),
                                    ],
                                  )
                                : Text(_isRegisterMode ? 'إنشاء حساب' : 'تسجيل الدخول'),
                          ),
                          if (_wakingServer) ...[
                            const SizedBox(height: 8),
                            Text(
                              'الخطة المجانية للسيرفر تحتاج حتى دقيقة للاستيقاظ بعد فترة خمول — المحاولة مستمرة تلقائيًا.',
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: 11.5, color: AppColors.greenDark),
                            ),
                          ],
                          if (_isNetworkError && !_loading) ...[
                            const SizedBox(height: 8),
                            OutlinedButton.icon(
                              onPressed: _submit,
                              icon: const Icon(Icons.refresh),
                              label: const Text('إعادة المحاولة'),
                            ),
                          ],
                          if (!_isRegisterMode) ...[
                            const SizedBox(height: 4),
                            TextButton(
                              onPressed: _loading ? null : () => setState(() => _isRegisterMode = true),
                              child: const Text('حساب جديد؟ أنشئ حسابًا',
                                  style: TextStyle(color: AppColors.textSecondary)),
                            ),
                          ],
                          const SizedBox(height: 6),
                          Row(
                            children: [
                              const Expanded(child: Divider()),
                              Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 10),
                                child: Text('أو',
                                    style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                              ),
                              const Expanded(child: Divider()),
                            ],
                          ),
                          const SizedBox(height: 6),
                          // الدخول بجوجل: يتطلب ربط حساب جوجل بحسابك على
                          // السيرفر (OAuth) — التهيئة موثقة في CI؛ حتى اكتمال
                          // الربط يظهر تنبيه واضح بدل الفشل الصامت.
                          OutlinedButton.icon(
                            onPressed: _loading ? null : _showGooglePendingInfo,
                            icon: const Icon(Icons.g_mobiledata, size: 26),
                            label: const Text('المتابعة بحساب Google'),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: AppColors.navy,
                              side: const BorderSide(color: AppColors.greyTint),
                              padding: const EdgeInsets.symmetric(vertical: 12),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                    // رقم الإصدار ظاهر دائمًا في شاشة الدخول — للتأكد فورًا أن
                    // الجهاز يعمل على آخر APK بعد التحديث.
                    const Text(
                      'حساباتك • إصدار ${AppConfig.appVersion}',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
