import { NextResponse } from 'next/server';
import sqlite3 from 'sqlite3';
import path from 'path';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export async function GET() {
  try {
    const dbPath = path.join(process.cwd(), '..', 'backend', 'data', 'analytics.db');
    
    // Connect to the DB and query it using a Promise
    const row: any = await new Promise((resolve, reject) => {
      const db = new sqlite3.Database(dbPath, sqlite3.OPEN_READONLY, (err) => {
        if (err) {
          reject(err);
        }
      });
      
      const query = `
        SELECT 
          COUNT(*) as total,
          SUM(CASE WHEN successful = 1 THEN 1 ELSE 0 END) as successful,
          SUM(CASE WHEN successful = 0 THEN 1 ELSE 0 END) as failed
        FROM calls
      `;
      
      db.get(query, [], (err, row) => {
        db.close();
        if (err) {
          reject(err);
        } else {
          resolve(row);
        }
      });
    });

    return NextResponse.json({
      total: row?.total || 0,
      successful: row?.successful || 0,
      failed: row?.failed || 0,
    });
  } catch (error) {
    console.error('Failed to fetch analytics:', error);
    return NextResponse.json({
      total: 0,
      successful: 0,
      failed: 0,
    });
  }
}
