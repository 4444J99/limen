export * from "./schema";
export * from "./epsilon-02";
import { MIGRATION_MANIFEST, CURRENT_SCHEMA_VERSION } from "./schema";

/**
 * Portable database bootstrap helper for migration-first development setups.
 */
export class DatabaseClient {
  private db: any = null;

  constructor(dbInstance?: any) {
    this.db = dbInstance;
  }

  public listMigrations(): string[] {
    return this.listMigrationsWithMetadata().map((entry) => entry.id);
  }

  public listMigrationsWithMetadata() {
    return MIGRATION_MANIFEST.map((entry: any) => ({ ...entry, currentSchemaVersion: CURRENT_SCHEMA_VERSION }));
  }

  public async initSchema(rawExec: (sql: string) => Promise<void> | void): Promise<void> {
    const { CREATE_TABLES_SQL } = await import("./schema");
    await rawExec(CREATE_TABLES_SQL);
  }
}
