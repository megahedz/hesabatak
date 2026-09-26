import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../core/session.dart';

/// First screen when there's no active session. Handles both login and
/// first-time registration (spec doesn't separate these into different
/// screens — a shop owner installing the app for the first time should
/// just get straight to "تسجيل الدخول / حساب جديد" without extra steps).
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  final _nameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isRegisterMode = false;
  bool _loading = false;
  String? _error;

  Future<void> _submit() async {
    final phone = _phoneController.text.trim();
    final password = _passwordController.text;
    if (phone.isEmpty || password.isEmpty || (_isRegisterMode && _nameController.text.trim().isEmpty)) {
      setState(() => _error = 'من فضلك أكمل كل البيانات المطلوبة');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = _isRegisterMode
          ? await _api.register(fullName: _nameController.text.trim(), phone: phone, password: password)
          : await _api.login(phone: phone, password: password);

      AppSession.instance.setAuth(
        token: result['access_token'] as String,
        userName: _isRegisterMode ? _nameController.text.trim() : phone,
      );

      await _resolveActiveCompany();
    } on ApiException catch (e) {
      setState(() => _error = e.statusCode == 401
          ? 'رقم الهاتف أو كلمة المرور غير صحيحة'
          : (_isRegisterMode ? 'تعذر إنشاء الحساب. جرّب رقم هاتف آخر.' : 'تعذر تسجيل الدخول. حاول مرة أخرى.'));
    } catch (e) {
      // TEMPORARY DEBUG: showing the real exception instead of a generic
      // message so we can see exactly what's failing. Revert this to the
      // friendly-only message once the bug is found (spec §49 normally
      // forbids showing raw technical errors to the user).
      setState(() => _error = 'تعذر الاتصال بالسيرفر.\n[DEBUG] ${e.toString()}');
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
    } catch (e) {
      // TEMPORARY DEBUG — see note above.
      if (mounted) {
        setState(() => _error = 'تعذر تجهيز الشركة.\n[DEBUG] ${e.toString()}');
      }
    }
  }

  Future<String?> _promptForCompanyName() {
    final controller = TextEditingController();
    return showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
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
              decoration: const InputDecoration(labelText: 'اسم المشروع أو المحل', border: OutlineInputBorder()),
            ),
          ],
        ),
        actions: [
          FilledButton(onPressed: () => Navigator.of(ctx).pop(controller.text.trim()), child: const Text('ابدأ الآن')),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Icon(Icons.account_balance_wallet_outlined, size: 56, color: Color(0xFF0F6E5C)),
                const SizedBox(height: 12),
                const Text('حساباتك', textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
                const Text('حسابات مشروعك ببساطة', textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.black54)),
                const SizedBox(height: 32),
                if (_isRegisterMode) ...[
                  TextField(
                    controller: _nameController,
                    decoration: const InputDecoration(labelText: 'الاسم', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 12),
                ],
                TextField(
                  controller: _phoneController,
                  keyboardType: TextInputType.phone,
                  decoration: const InputDecoration(labelText: 'رقم الهاتف', border: OutlineInputBorder()),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _passwordController,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: 'كلمة المرور', border: OutlineInputBorder()),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  SelectableText(_error!, style: const TextStyle(color: Colors.redAccent), textAlign: TextAlign.center),
                ],
                const SizedBox(height: 20),
                FilledButton(
                  onPressed: _loading ? null : _submit,
                  child: _loading
                      ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : Text(_isRegisterMode ? 'إنشاء حساب' : 'تسجيل الدخول'),
                ),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: _loading ? null : () => setState(() => _isRegisterMode = !_isRegisterMode),
                  child: Text(_isRegisterMode ? 'لديك حساب بالفعل؟ سجّل الدخول' : 'حساب جديد؟ أنشئ حسابًا'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
