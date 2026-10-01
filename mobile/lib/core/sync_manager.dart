import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'app_config.dart';
import 'local_store.dart';

/// Online/offline state for the status banner.
///
/// ARCHITECTURE (mandatory): offline mode is NOT supported anymore — the
/// server's cloud database is the single source of truth and writes are
/// online-only. This manager no longer queues anything. Its only remaining
/// job is a one-time DRAIN of a legacy queue that app versions before the
/// cloud-architecture update could have left on the device, so operations
/// recorded before the update are uploaded once and never lost.
class SyncManager extends ChangeNotifier {
  SyncManager._();
  static final SyncManager instance = SyncManager._();

  final LocalStore _store = LocalStore.instance;
  StreamSubscription<List<ConnectivityResult>>? _sub;
  bool _online = true;
  int _pending = 0;
  bool _flushing = false;
  Timer? _retryTimer;

  bool get isOnline => _online;
  int get pendingCount => _pending;

  /// Called once from main() after session restore. Starts the connectivity
  /// listener for the banner and drains any legacy queued writes exactly once.
  Future<void> start() async {
    try {
      _sub = Connectivity().onConnectivityChanged.listen((results) {
        final hasNetwork = results.any((r) => r != ConnectivityResult.none);
        if (_online != hasNetwork) {
          _online = hasNetwork;
          notifyListeners();
        }
      });
    } catch (_) {
      // Plugin unavailable: assume online; writes simply follow their own
      // success/failure path.
      _online = true;
    }
    // One-time drain of a legacy queue from older app versions.
    await drainLegacyQueue();
  }

  Future<void> _refreshPending() async {
    try {
      _pending = await _store.queueLength();
    } catch (_) {
      _pending = 0;
    }
    notifyListeners();
  }

  /// Uploads any operations left by a pre-cloud-architecture version, FIFO,
  /// then clears them. Never queue new writes — this only runs at startup.
  Future<void> drainLegacyQueue() async {
    await _refreshPending();
    if (_pending == 0 || _flushing) return;
    _flushing = true;
    try {
      final writes = await _store.pendingWrites();
      final api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
      for (final w in writes) {
        try {
          await api.sendQueued(w.endpoint, w.params);
          await _store.deleteQueued(w.id);
        } on ApiException catch (e) {
          // Invalid operation (4xx): drop it rather than poison the drain.
          // 401/5xx/network: stop and retry on the next app start.
          if (e.statusCode == 401 || e.statusCode >= 500) break;
          await _store.deleteQueued(w.id);
        } catch (_) {
          break; // network-level failure — retry next start
        }
      }
    } finally {
      _flushing = false;
      await _refreshPending();
    }
  }

  /// Kept as a no-op alias so any stray caller compiles; nothing is ever
  /// queued anymore.
  Future<int> enqueueOfflineWrite(String endpoint, Map<String, String> params) async {
    await _refreshPending();
    return _pending;
  }

  /// Legacy alias for the one-time drain (the old banner button called it).
  Future<void> flush() => drainLegacyQueue();

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }
}
