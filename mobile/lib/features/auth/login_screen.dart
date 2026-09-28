import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../core/session.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';

/// شاشة الدخول — نفس لغة التصميم المرجعي: خلفية فاتحة بلمسات زرقاء ناعمة،
/// شعار حساباتك في الأعلى، ثم بطاقة بيضاء بها الحقول وزر أزرق «تسجيل الدخول».
/// تتعامل مع الدخول وإنشاء الحساب الأول معًا (spec §56/§57).
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

  Future<void> _submit() async {
    final phone = _phoneController.text.trim();
    final password = _passwordController.text;
    final email = _emailController.text.trim();
    if (_isRegisterMode && _nameController.text.trim().isEmpty) {
      setState(() => _error = 'من فضلك أكمل كل البيانات المطلوبة');
      return;
    }
    // البريد إجباري عند إنشاء الحساب (spec: إجباري مقترح ✓)
    if (_isRegisterMode && !_emailRe.hasMatch(email)) {
      setState(() => _error = 'من فضلك أدخل بريدًا إلكترونيًا صحيحًا (مثال: name@example.com)');
      return;
    }
    // تحقق محلي من كلمة المرور قبل إرسال أي شيء للسيرفر
    if (_isRegisterMode &&
        (password.length < 8 || !password.contains(RegExp(r'[A-Za-z]')) || !password.contains(RegExp(r'\d')))) {
      setState(() => _error = 'كلمة المرور يجب أن تكون 8 أحرف على الأقل وتحتوي على حرف ورقم واحد على الأقل');
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
    });
    try {
      final result = _isRegisterMode
          ? await _api.register(
              fullName: _nameController.text.trim(), phone: phone, email: email, password: password)
          : await _api.login(phone: phone, password: password);

      AppSession.instance.setAuth(
        token: result['access_token'] as String,
        userName: _isRegisterMode ? _nameController.text.trim() : phone,
        userEmail: _isRegisterMode ? email : null,
      );

      await _resolveActiveCompany();
    } on ApiException catch (e) {
      setState(() => _error = e.statusCode == 401
          ? 'رقم الهاتف أو كلمة المرور غير صحيحة'
          : (_isRegisterMode ? 'تعذر إنشاء الحساب. جرّب رقم هاتف آخر.' : 'تعذر تسجيل الدخول. حاول مرة أخرى.'));
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
          ? 'تعذر إنشاء الحساب. جرّب رقم هاتف آخر.'
          : 'تعذر تسجيل الدخول. حاول مرة أخرى.');
    } finally {
      if (mounted) setState(() => _loading = false);
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
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const HesabatakLogo(size: 96),
                  const SizedBox(height: 12),
                  const Text('حساباتك',
                      style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: AppColors.navy)),
                  const SizedBox(height: 4),
                  const Text('إدارة أعمالك بسهولة',
                      style: TextStyle(fontSize: 14, color: AppColors.textSecondary)),
                  const SizedBox(height: 28),
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
                            labelText: 'اسم المستخدم (رقم الهاتف)',
                            prefixIcon: Icon(Icons.person_outline),
                          ),
                        ),
                        const SizedBox(height: 14),
                        TextField(
                          controller: _passwordController,
                          obscureText: _obscure,
                          onChanged: (_) => setState(() {}),
                          decoration: InputDecoration(
                            labelText: _isRegisterMode ? 'كلمة المرور (8 أحرف على الأقل مع رقم)' : 'كلمة المرور',
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
                                                  : AppColors.green)
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
                              color: _passwordStrength < 2 ? AppColors.red : AppColors.green,
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
                                    onChanged: (v) => setState(() => _rememberMe = v ?? true),
                                  ),
                                ),
                                const SizedBox(width: 6),
                                const Text('تذكّني', style: TextStyle(fontSize: 13.5, color: AppColors.navy)),
                              ],
                            ),
                            TextButton(
                              onPressed: () => setState(() => _isRegisterMode = !_isRegisterMode),
                              child: Text(
                                _isRegisterMode ? 'لديك حساب؟ سجّل الدخول' : 'نسيت كلمة المرور؟',
                                style: const TextStyle(fontSize: 13, color: AppColors.primary),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        FilledButton(
                          onPressed: _loading ? null : _submit,
                          child: _loading
                              ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                              : Text(_isRegisterMode ? 'إنشاء حساب' : 'تسجيل الدخول'),
                        ),
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
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
