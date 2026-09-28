import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../home/home_shell.dart';

/// إدارة الفريق (Phase 7) — للمالك فقط: أعضاء الشركة وأدوارهم،
/// إضافة عضو برقم هاتفه، تغيير الدور، أو الإزالة.
/// الأدوار: owner مالك (كل الصلاحيات) / accountant محاسب (تسجيل وتقارير) /
/// staff موظف (عرض فقط).
class TeamScreen extends StatefulWidget {
  const TeamScreen({super.key});

  @override
  State<TeamScreen> createState() => _TeamScreenState();
}

class _TeamScreenState extends State<TeamScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  List<dynamic> _team = const [];
  String _myRole = 'staff';
  bool _loading = true;
  bool _failed = false;

  bool get _isOwner => _myRole == 'owner';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _failed = false;
    });
    try {
      final results = await Future.wait([
        _api.getTeam(AppConfig.companyId),
        _api.getMyMembership(AppConfig.companyId),
      ]);
      if (!mounted) return;
      setState(() {
        _team = results[0] as List<dynamic>;
        _myRole = (results[1] as Map<String, dynamic>)['role'] as String? ?? 'staff';
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

  String get _roleLabel {
    switch (_myRole) {
      case 'owner':
        return 'مالك';
      case 'accountant':
        return 'محاسب';
      default:
        return 'موظف';
    }
  }

  Future<void> _addMember() async {
    final phone = TextEditingController();
    String role = 'staff';
    bool saving = false;

    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (sheetCtx) => StatefulBuilder(
        builder: (sheetCtx, setSheetState) => Padding(
          padding: EdgeInsets.only(
            left: 20, right: 20, top: 20,
            bottom: MediaQuery.of(sheetCtx).viewInsets.bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('إضافة عضو',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.navy)),
              const SizedBox(height: 6),
              const Text(
                'يجب أن يكون المستخدم قد أنشأ حسابًا في حساباتك أولًا (برقم هاتفه).',
                style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: phone,
                autofocus: true,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                    labelText: 'رقم الهاتف', prefixIcon: Icon(Icons.phone_outlined, size: 20)),
              ),
              const SizedBox(height: 12),
              const Text('الدور', style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
              const SizedBox(height: 6),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'accountant', label: Text('محاسب')),
                  ButtonSegment(value: 'staff', label: Text('موظف')),
                ],
                selected: {role},
                onSelectionChanged: (s) => setSheetState(() => role = s.first),
              ),
              const SizedBox(height: 14),
              FilledButton(
                onPressed: saving
                    ? null
                    : () async {
                        if (phone.text.trim().isEmpty) {
                          ScaffoldMessenger.of(context)
                              .showSnackBar(const SnackBar(content: Text('أدخل رقم الهاتف')));
                          return;
                        }
                        setSheetState(() => saving = true);
                        try {
                          await _api.addTeamMember(AppConfig.companyId,
                              phone: phone.text.trim(), role: role);
                          if (sheetCtx.mounted) Navigator.of(sheetCtx).pop(true);
                        } on ApiException catch (e) {
                          if (sheetCtx.mounted) Navigator.of(sheetCtx).pop(false);
                          if (mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                                content: Text(e.statusCode == 404
                                    ? 'لا يوجد حساب بهذا الرقم — اطلب منه التسجيل أولًا'
                                    : e.statusCode == 400
                                        ? 'هذا المستخدم عضو بالفعل'
                                        : 'تعذر إضافة العضو. حاول مرة أخرى.')));
                          }
                        } catch (_) {
                          if (sheetCtx.mounted) Navigator.of(sheetCtx).pop(false);
                          if (mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('تعذر إضافة العضو. حاول مرة أخرى.')));
                          }
                        } finally {
                          setSheetState(() => saving = false);
                        }
                      },
                child: saving
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('إضافة العضو'),
              ),
            ],
          ),
        ),
      ),
    );
    if (ok == true && mounted) _load();
    phone.dispose();
  }

  Future<void> _changeRole(Map<String, dynamic> member) async {
    final current = member['role'] as String;
    final picked = await showModalBottomSheet<String>(
      context: context,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (sheetCtx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.all(12),
              child: Text('تغيير الدور',
                  style: TextStyle(fontWeight: FontWeight.w800, color: AppColors.navy)),
            ),
            for (final (label, value) in const [('مالك', 'owner'), ('محاسب', 'accountant'), ('موظف', 'staff')])
              ListTile(
                title: Text(label),
                trailing: current == value ? const Icon(Icons.check, color: AppColors.primary) : null,
                onTap: () => Navigator.of(sheetCtx).pop(value),
              ),
          ],
        ),
      ),
    );
    if (picked == null || picked == current) return;
    try {
      await _api.changeMemberRole(AppConfig.companyId,
          userId: member['user_id'] as int, role: picked);
      _load();
    } on ApiException {
      _toast('تعذر تغيير الدور');
    } catch (_) {
      _toast('تعذر تغيير الدور. حاول مرة أخرى.');
    }
  }

  Future<void> _removeMember(Map<String, dynamic> member) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogCtx) => Directionality(
        textDirection: TextDirection.rtl,
        child: AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Text('إزالة العضو'),
          content: Text('سيتم إزالة ${member['full_name']} من الوصول إلى بيانات هذه الشركة. بياناته المحاسبية ستبقى كما هي.'),
          actions: [
            TextButton(onPressed: () => Navigator.of(dialogCtx).pop(false), child: const Text('إلغاء')),
            FilledButton(
              onPressed: () => Navigator.of(dialogCtx).pop(true),
              style: FilledButton.styleFrom(backgroundColor: AppColors.red),
              child: const Text('إزالة'),
            ),
          ],
        ),
      ),
    );
    if (confirmed != true) return;
    try {
      await _api.removeTeamMember(AppConfig.companyId, userId: member['user_id'] as int);
      _load();
    } on ApiException catch (e) {
      _toast(e.statusCode == 400 ? 'لا يمكن إزالة المالك الوحيد للشركة' : 'تعذر إزالة العضو');
    } catch (_) {
      _toast('تعذر إزالة العضو. حاول مرة أخرى.');
    }
  }

  void _toast(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(title: 'فريق العمل', showMenu: false),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _failed
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text('تعذر تحميل الفريق. تأكد من الاتصال.',
                          style: TextStyle(color: AppColors.textSecondary)),
                      const SizedBox(height: 12),
                      FilledButton(onPressed: _load, child: const Text('إعادة المحاولة')),
                    ],
                  ),
                )
              : RefreshIndicator(
                  color: AppColors.primary,
                  onRefresh: () async => _load(),
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      SectionCard(
                        child: Row(
                          children: [
                            const IconTile(
                              icon: Icons.badge_rounded,
                              background: AppColors.blueTint,
                              color: AppColors.primary,
                              size: 44,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('${_team.length} أعضاء',
                                      style: const TextStyle(
                                          fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.navy)),
                                  Text('دورك: $_roleLabel',
                                      style: const TextStyle(
                                          fontSize: 12, color: AppColors.textSecondary)),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),
                      if (_isOwner)
                        FilledButton.icon(
                          onPressed: _addMember,
                          icon: const Icon(Icons.person_add_rounded, size: 20),
                          label: const Text('إضافة عضو'),
                        ),
                      if (_isOwner) const SizedBox(height: 14),
                      SectionCard(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                        child: Column(
                          children: [
                            for (final member in _team)
                              AppListTile(
                                icon: Icons.person_rounded,
                                title: member['full_name'] as String? ?? '',
                                subtitle: _roleText(member['role'] as String? ?? 'staff'),
                                trailingChevron: _isOwner,
                                onTap: _isOwner ? () => _memberActions(member) : null,
                              ),
                            if (_team.isEmpty)
                              const Padding(
                                padding: EdgeInsets.symmetric(vertical: 18),
                                child: Text('لا يوجد أعضاء بعد',
                                    style: TextStyle(color: AppColors.textSecondary)),
                              ),
                          ],
                        ),
                      ),
                      if (_isOwner) ...[
                        const SizedBox(height: 8),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 4),
                          child: Text(
                            'اضغط على أي عضو لتغيير دوره أو إزالته.',
                            style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
    );
  }

  /// قائمة إجراءات المالك على عضو: تغيير الدور أو الإزالة.
  Future<void> _memberActions(Map<String, dynamic> member) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (sheetCtx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.all(12),
              child: Text(member['full_name'] as String? ?? '',
                  style: const TextStyle(fontWeight: FontWeight.w800, color: AppColors.navy)),
            ),
            ListTile(
              leading: const Icon(Icons.manage_accounts_rounded, color: AppColors.primary),
              title: const Text('تغيير الدور'),
              onTap: () => Navigator.of(sheetCtx).pop('role'),
            ),
            ListTile(
              leading: const Icon(Icons.person_remove_rounded, color: AppColors.red),
              title: const Text('إزالة من الشركة'),
              onTap: () => Navigator.of(sheetCtx).pop('remove'),
            ),
          ],
        ),
      ),
    );
    if (action == 'role') await _changeRole(member);
    if (action == 'remove') await _removeMember(member);
  }

  String _roleText(String role) {
    switch (role) {
      case 'owner':
        return 'مالك — كل الصلاحيات';
      case 'accountant':
        return 'محاسب — تسجيل العمليات والتقارير';
      default:
        return 'موظف — عرض فقط';
    }
  }
}
