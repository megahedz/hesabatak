import 'dart:convert';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

/// بديل فارغ عند التشغيل على الويب (sqflite غير مدعوم في المتصفح):
/// الكاش وطابور المزامنة معطّلان على الويب — التطبيق يعمل online-only هناك.

/// Phase 6 offline-first store (spec §42/§43):
///
///  * `cache`      — last-known server payload per key (e.g. "dashboard",
///                   "customers", "reports_sales"), so every screen opens
///                   instantly with the previous data even with no network.
///  * `sync_queue` — every write made while offline, in order, replayed FIFO
///                   by [SyncManager.flush] when connectivity returns.
///
/// Plain sqflite (pure-Dart API) keeps this platform-folder-free and works
/// with the CI-generated Android scaffold out of the box.
class LocalStore {
  LocalStore._();
  static final LocalStore instance = LocalStore._();

  static const _dbName = 'hesabatak_local.db';
  Database? _db;

  Future<Database> get db async {
    if (kIsWeb) {
      throw UnsupportedError('sqflite is not available on the web');
    }
    final existing = _db;
    if (existing != null && existing.isOpen) return existing;
    final databasesPath = await getDatabasesPath();
    _db = await openDatabase(
      p.join(databasesPath, _dbName),
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE cache (
            cache_key TEXT PRIMARY KEY,
            payload   TEXT NOT NULL,
            saved_at  TEXT NOT NULL
          )
        ''');
        await db.execute('''
          CREATE TABLE sync_queue (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint  TEXT NOT NULL,
            params    TEXT NOT NULL,
            created_at TEXT NOT NULL
          )
        ''');
      },
    );
    return _db!;
  }

  // ---------------------------------------------------------------- cache
  Future<void> saveCache(String key, Map<String, dynamic> payload) async {
    final database = await db;
    await database.insert(
      'cache',
      {
        'cache_key': key,
        'payload': jsonEncode(payload),
        'saved_at': DateTime.now().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<Map<String, dynamic>?> readCache(String key) async {
    final database = await db;
    final rows = await database.query('cache',
        where: 'cache_key = ?', whereArgs: [key], limit: 1);
    if (rows.isEmpty) return null;
    try {
      return jsonDecode(rows.first['payload'] as String) as Map<String, dynamic>;
    } catch (_) {
      return null; // corrupted row → behave as a cache miss
    }
  }

  // ----------------------------------------------------------- sync queue
  /// Enqueue one offline write. Returns the queue length after inserting.
  Future<int> enqueue(String endpoint, Map<String, String> params) async {
    final database = await db;
    await database.insert('sync_queue', {
      'endpoint': endpoint,
      'params': jsonEncode(params),
      'created_at': DateTime.now().toIso8601String(),
    });
    final row = await database.rawQuery('SELECT COUNT(*) AS n FROM sync_queue');
    return (row.first['n'] as int?) ?? 1;
  }

  Future<int> queueLength() async {
    final database = await db;
    final row = await database.rawQuery('SELECT COUNT(*) AS n FROM sync_queue');
    return (row.first['n'] as int?) ?? 0;
  }

  Future<List<QueuedWrite>> pendingWrites() async {
    final database = await db;
    final rows = await database.query('sync_queue', orderBy: 'id ASC');
    return rows.map((r) {
      Map<String, String> params = const {};
      try {
        params = (jsonDecode(r['params'] as String) as Map<String, dynamic>)
            .map((k, v) => MapEntry(k, v.toString()));
      } catch (_) {}
      return QueuedWrite(
        id: r['id'] as int,
        endpoint: r['endpoint'] as String,
        params: params,
      );
    }).toList();
  }

  Future<void> deleteQueued(int id) async {
    final database = await db;
    await database.delete('sync_queue', where: 'id = ?', whereArgs: [id]);
  }
}

class QueuedWrite {
  QueuedWrite({required this.id, required this.endpoint, required this.params});
  final int id;
  final String endpoint;
  final Map<String, String> params;
}
