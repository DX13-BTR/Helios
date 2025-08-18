import datetime
from ..modules.fss.fss_summary import calculate_fss_summary
from ..modules.fss.generate_fss_advice import generate_fss_advice
from ..db.database import get_db_connection

def log_run(status, message):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS fss_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, status TEXT, message TEXT
        )''')
        cur.execute('INSERT INTO fss_runs (timestamp, status, message) VALUES (?, ?, ?)',
                    (datetime.datetime.now().isoformat(), status, message))
        conn.commit()

def run_fss_pipeline():
    log_run('STARTED', 'FSS pipeline execution started')
    try:
        calculate_fss_summary()
        generate_fss_advice()
        log_run('SUCCESS', 'FSS pipeline completed: overall advice generated')
        print('✅ FSS 2.0 pipeline complete. Advice saved to DB.')
    except Exception as e:
        log_run('FAILED', f'Error: {e}')
        raise

if __name__ == '__main__':
    run_fss_pipeline()
