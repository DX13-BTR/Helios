# recurring_task_analyzer.py
"""
Analyze ClickUp extraction JSON to find recurring tasks by identifying:
1. Tasks with identical names (indicating recurrence)
2. Their due date patterns (daily, weekly, monthly, etc.)
3. Generate Helios migration data for proper recurring tasks
"""

import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Any
import statistics

def analyze_recurring_patterns(json_file_path: str):
    """
    Analyze the ClickUp extraction to find recurring task patterns
    """
    print(f"📁 Loading ClickUp extraction from {json_file_path}...")
    
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    tasks = data.get('tasks', [])
    print(f"📊 Found {len(tasks)} total tasks")
    
    # Group tasks by exact name
    tasks_by_name = defaultdict(list)
    for task in tasks:
        name = task.get('name', '').strip()
        if name:  # Skip empty names
            tasks_by_name[name].append(task)
    
    print(f"📋 Found {len(tasks_by_name)} unique task names")
    
    # Find recurring tasks (names that appear multiple times)
    recurring_tasks = {}
    one_time_tasks = {}
    
    for name, task_list in tasks_by_name.items():
        if len(task_list) > 1:
            recurring_tasks[name] = task_list
        else:
            one_time_tasks[name] = task_list[0]
    
    print(f"🔄 Found {len(recurring_tasks)} recurring task types")
    print(f"📝 Found {len(one_time_tasks)} one-time tasks")
    
    # Analyze each recurring task pattern
    recurring_analysis = []
    
    for name, task_instances in recurring_tasks.items():
        print(f"\n🔍 Analyzing: '{name}' ({len(task_instances)} instances)")
        
        # Extract due dates
        due_dates = []
        statuses = []
        
        for task in task_instances:
            # ClickUp due_date is in milliseconds
            due_date_ms = task.get('due_date')
            if due_date_ms:
                try:
                    due_date = datetime.fromtimestamp(int(due_date_ms) / 1000)
                    due_dates.append(due_date)
                except:
                    continue
            
            # Get status
            status = task.get('status', {})
            if isinstance(status, dict):
                statuses.append(status.get('status', 'unknown'))
            else:
                statuses.append(str(status))
        
        if len(due_dates) < 2:
            continue
            
        # Sort by due date
        due_dates.sort()
        
        # Calculate intervals between consecutive due dates
        intervals = []
        for i in range(1, len(due_dates)):
            delta = due_dates[i] - due_dates[i-1]
            intervals.append(delta.days)
        
        # Determine recurrence pattern
        if intervals:
            avg_interval = statistics.mean(intervals)
            interval_mode = Counter(intervals).most_common(1)[0][0] if intervals else 0
            
            # Classify recurrence pattern
            if 0.8 <= avg_interval <= 1.2:
                pattern = "daily"
                interval = 1
            elif 6.5 <= avg_interval <= 7.5:
                pattern = "weekly"  
                interval = 7
            elif 13 <= avg_interval <= 15:
                pattern = "fortnightly"
                interval = 14
            elif 28 <= avg_interval <= 32:
                pattern = "monthly"
                interval = 30
            elif 85 <= avg_interval <= 95:
                pattern = "quarterly"
                interval = 90
            elif 360 <= avg_interval <= 370:
                pattern = "annual"
                interval = 365
            else:
                pattern = "irregular"
                interval = int(avg_interval)
        else:
            pattern = "unknown"
            interval = 0
        
        # Get sample task for metadata
        sample_task = task_instances[0]
        
        analysis = {
            'name': name,
            'total_instances': len(task_instances),
            'pattern': pattern,
            'interval_days': interval,
            'avg_interval': round(avg_interval, 1) if intervals else 0,
            'date_range': {
                'first': due_dates[0].isoformat() if due_dates else None,
                'last': due_dates[-1].isoformat() if due_dates else None,
                'span_days': (due_dates[-1] - due_dates[0]).days if len(due_dates) >= 2 else 0
            },
            'status_breakdown': dict(Counter(statuses)),
            'metadata': {
                'list_name': sample_task.get('parent_list_name', ''),
                'folder_name': sample_task.get('parent_folder_name', ''),
                'space_name': sample_task.get('parent_space_name', ''),
                'priority': sample_task.get('priority', {}),
                'assignees': [a.get('username', '') for a in sample_task.get('assignees', [])],
                'tags': [t.get('name', '') for t in sample_task.get('tags', [])],
                'description': sample_task.get('text_content', '')[:200] + ('...' if len(sample_task.get('text_content', '')) > 200 else '')
            },
            'sample_due_dates': [d.strftime('%Y-%m-%d') for d in due_dates[:10]]  # First 10 dates
        }
        
        recurring_analysis.append(analysis)
    
    # Sort by total instances (most recurring first)
    recurring_analysis.sort(key=lambda x: x['total_instances'], reverse=True)
    
    # Generate summary statistics
    total_recurring_instances = sum(a['total_instances'] for a in recurring_analysis)
    pattern_counts = Counter(a['pattern'] for a in recurring_analysis)
    
    summary = {
        'total_tasks': len(tasks),
        'unique_task_names': len(tasks_by_name),
        'recurring_task_types': len(recurring_tasks),
        'one_time_tasks': len(one_time_tasks),
        'total_recurring_instances': total_recurring_instances,
        'pattern_distribution': dict(pattern_counts),
        'top_recurring_tasks': recurring_analysis[:20]  # Top 20 most recurring
    }
    
    return {
        'summary': summary,
        'all_recurring_tasks': recurring_analysis,
        'extraction_metadata': data.get('metadata', {})
    }

def save_recurring_analysis(analysis: Dict, output_file: str = "helios_recurring_analysis.json"):
    """Save the analysis to a JSON file"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"💾 Analysis saved to {output_file}")

def print_recurring_summary(analysis: Dict):
    """Print a human-readable summary of recurring tasks"""
    summary = analysis['summary']
    
    print("\n" + "="*80)
    print("📊 CLICKUP RECURRING TASK ANALYSIS SUMMARY")
    print("="*80)
    
    print(f"Total tasks extracted: {summary['total_tasks']:,}")
    print(f"Unique task names: {summary['unique_task_names']:,}")
    print(f"Recurring task types: {summary['recurring_task_types']:,}")
    print(f"One-time tasks: {summary['one_time_tasks']:,}")
    print(f"Total recurring instances: {summary['total_recurring_instances']:,}")
    
    print(f"\nRecurrence pattern distribution:")
    for pattern, count in summary['pattern_distribution'].items():
        print(f"  {pattern}: {count} task types")
    
    print(f"\n🔄 TOP 20 MOST RECURRING TASKS:")
    print("-" * 80)
    
    for i, task in enumerate(summary['top_recurring_tasks'], 1):
        status_summary = ", ".join([f"{k}: {v}" for k, v in task['status_breakdown'].items()])
        
        print(f"{i:2d}. {task['name']}")
        print(f"    📅 Pattern: {task['pattern']} ({task['interval_days']} days)")  
        print(f"    📊 Instances: {task['total_instances']} | Status: {status_summary}")
        print(f"    📂 Location: {task['metadata']['space_name']} > {task['metadata']['folder_name']} > {task['metadata']['list_name']}")
        print(f"    📆 Date range: {task['date_range']['first'][:10]} to {task['date_range']['last'][:10]} ({task['date_range']['span_days']} days)")
        if task['metadata']['description']:
            print(f"    📝 Description: {task['metadata']['description']}")
        print()

if __name__ == "__main__":
    # Analyze the ClickUp extraction
    json_file = "clickup_complete_extraction_1755930408.json"  # Your extraction file
    
    print("🚀 Starting ClickUp Recurring Task Analysis...")
    
    try:
        analysis = analyze_recurring_patterns(json_file)
        
        # Print summary to console
        print_recurring_summary(analysis)
        
        # Save detailed analysis to file
        save_recurring_analysis(analysis)
        
        print("\n✅ Analysis complete! Check helios_recurring_analysis.json for full details.")
        
    except FileNotFoundError:
        print(f"❌ File not found: {json_file}")
        print("Make sure the ClickUp extraction file is in the current directory.")
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()