# core_py/clickup_complete_extractor.py
import json
import time
import requests
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ExtractionStats:
    spaces: int = 0
    folders: int = 0  
    lists: int = 0
    tasks: int = 0
    users: int = 0
    custom_fields: int = 0
    dependencies: int = 0
    recurring_tasks: int = 0

class ClickUpCompleteExtractor:
    """
    Comprehensive ClickUp data extractor for complete migration to Helios.
    Extracts ALL organizational structure, tasks, relationships, and metadata.
    """
    
    def __init__(self, api_key: str, team_id: str):
        self.api_key = api_key
        self.team_id = team_id
        self.base_url = "https://api.clickup.com/api/v2"
        self.headers = {"Authorization": api_key}
        self.stats = ExtractionStats()
        
        # Cache for avoiding duplicate calls
        self._cached_spaces = None
        self._cached_folders = None
        self._cached_lists = None
        
    def _request(self, endpoint: str, params: dict = None) -> dict:
        """Make rate-limited ClickUp API request"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            # Handle rate limiting
            if response.status_code == 429:
                print(f"⏳ Rate limited, waiting 60 seconds...")
                time.sleep(60)
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ API request failed for {endpoint}: {e}")
            return {}

    def get_all_spaces(self) -> List[Dict]:
        """Extract all spaces in the team"""
        if self._cached_spaces is not None:
            return self._cached_spaces
            
        print("📁 Extracting spaces...")
        data = self._request(f"/team/{self.team_id}/space")
        spaces = data.get("spaces", [])
        
        # Enrich spaces with folder/list counts
        for space in spaces:
            space_folders = self._request(f"/space/{space['id']}/folder")
            space['folder_count'] = len(space_folders.get("folders", []))
            
        self.stats.spaces = len(spaces)
        self._cached_spaces = spaces
        print(f"✅ Found {len(spaces)} spaces")
        return spaces

    def get_all_folders(self) -> List[Dict]:
        """Extract all folders across all spaces"""
        if self._cached_folders is not None:
            return self._cached_folders
            
        print("📂 Extracting folders...")
        all_folders = []
        
        # Get spaces first
        spaces = self.get_all_spaces()
        
        for space in spaces:
            data = self._request(f"/space/{space['id']}/folder")
            folders = data.get("folders", [])
            
            # Add space context to each folder
            for folder in folders:
                folder['parent_space_id'] = space['id']
                folder['parent_space_name'] = space['name']
                
            all_folders.extend(folders)
            
        self.stats.folders = len(all_folders)
        self._cached_folders = all_folders
        print(f"✅ Found {len(all_folders)} folders")
        return all_folders

    def get_all_lists(self) -> List[Dict]:
        """Extract all lists from all spaces and folders"""
        if self._cached_lists is not None:
            return self._cached_lists
            
        print("📋 Extracting lists...")
        all_lists = []
        
        # Get lists from spaces (folderless lists)
        spaces = self.get_all_spaces()
        for space in spaces:
            data = self._request(f"/space/{space['id']}/list")
            lists = data.get("lists", [])
            
            for lst in lists:
                lst['parent_space_id'] = space['id']
                lst['parent_space_name'] = space['name']
                lst['parent_folder_id'] = None
                lst['parent_folder_name'] = None
                
            all_lists.extend(lists)
            
        # Get lists from folders  
        folders = self.get_all_folders()
        for folder in folders:
            data = self._request(f"/folder/{folder['id']}/list")
            lists = data.get("lists", [])
            
            for lst in lists:
                lst['parent_space_id'] = folder.get('parent_space_id')
                lst['parent_space_name'] = folder.get('parent_space_name')
                lst['parent_folder_id'] = folder['id']
                lst['parent_folder_name'] = folder['name']
                
            all_lists.extend(lists)
            
        self.stats.lists = len(all_lists)
        self._cached_lists = all_lists
        print(f"✅ Found {len(all_lists)} lists")
        return all_lists

    def get_all_tasks_with_recurrence(self) -> List[Dict]:
        """Extract ALL tasks with full metadata including recurrence patterns"""
        print("⚡ Extracting all tasks with full metadata...")
        all_tasks = []
        
        # Get tasks from all lists
        lists = self.get_all_lists()
        
        for lst in lists:
            print(f"  📋 Processing list: {lst['name']}")
            
            # Get tasks in batches with all metadata
            page = 0
            while True:
                params = {
                    "archived": "false",
                    "page": page,
                    "order_by": "created",
                    "reverse": "false",
                    "subtasks": "true",
                    "include_closed": "true"
                }
                
                data = self._request(f"/list/{lst['id']}/task", params)
                tasks = data.get("tasks", [])
                
                if not tasks:
                    break
                    
                # Enrich each task with context and recurrence data
                for task in tasks:
                    # Add list/folder/space context
                    task['parent_list_id'] = lst['id']
                    task['parent_list_name'] = lst['name']
                    task['parent_folder_id'] = lst.get('parent_folder_id')
                    task['parent_folder_name'] = lst.get('parent_folder_name')
                    task['parent_space_id'] = lst.get('parent_space_id')
                    task['parent_space_name'] = lst.get('parent_space_name')
                    
                    # Extract recurrence pattern from custom fields
                    recurrence_info = self._extract_recurrence_pattern(task)
                    task['helios_recurrence'] = recurrence_info
                    
                    # Get full task details including dependencies
                    full_task = self._request(f"/task/{task['id']}")
                    if full_task:
                        task.update(full_task)
                        
                    if recurrence_info['is_recurring']:
                        self.stats.recurring_tasks += 1
                        
                all_tasks.extend(tasks)
                page += 1
                
                # Progress update
                if page % 10 == 0:
                    print(f"    📦 Processed {len(all_tasks)} tasks so far...")
                    
        self.stats.tasks = len(all_tasks)
        print(f"✅ Found {len(all_tasks)} total tasks ({self.stats.recurring_tasks} recurring)")
        return all_tasks

    def _extract_recurrence_pattern(self, task: dict) -> dict:
        """Extract and normalize recurrence pattern from ClickUp custom fields"""
        recurrence_info = {
            'is_recurring': False,
            'pattern': 'one_time',
            'interval': 1,
            'clickup_recurrence_field': None
        }
        
        # Look for recurrence in custom fields
        custom_fields = task.get('custom_fields', [])
        for field in custom_fields:
            field_name = field.get('name', '').lower()
            
            if 'recurrence' in field_name or 'recurring' in field_name or 'repeat' in field_name:
                recurrence_info['clickup_recurrence_field'] = field
                
                # Extract pattern from field value
                if field.get('value'):
                    options = field.get('type_config', {}).get('options', [])
                    selected_option = None
                    
                    # Find selected option
                    if isinstance(field['value'], dict):
                        selected_option = field['value']
                    elif isinstance(field['value'], list) and len(field['value']) > 0:
                        selected_option = field['value'][0]
                        
                    if selected_option:
                        option_name = selected_option.get('name', '').lower()
                        recurrence_info['is_recurring'] = option_name not in ['none', 'one_time', 'ad hoc']
                        
                        # Map ClickUp patterns to Helios patterns
                        pattern_mapping = {
                            'daily': 'daily',
                            'weekly': 'weekly', 
                            'fortnightly': 'weekly',  # 2-week interval
                            'monthly': 'monthly',
                            'quarterly': 'quarterly',
                            'annually': 'annual',
                            'yearly': 'annual'
                        }
                        
                        for clickup_pattern, helios_pattern in pattern_mapping.items():
                            if clickup_pattern in option_name:
                                recurrence_info['pattern'] = helios_pattern
                                if clickup_pattern == 'fortnightly':
                                    recurrence_info['interval'] = 2
                                break
                                
        return recurrence_info

    def get_all_users(self) -> List[Dict]:
        """Extract all team members"""
        print("👥 Extracting users...")
        data = self._request(f"/team/{self.team_id}")
        team_data = data.get("team", {})
        users = team_data.get("members", [])
        
        self.stats.users = len(users)
        print(f"✅ Found {len(users)} users")
        return users

    def get_all_custom_fields(self) -> List[Dict]:
        """Extract all custom field definitions"""
        print("🏷️ Extracting custom fields...")
        all_fields = []
        
        lists = self.get_all_lists()
        
        for lst in lists:
            # Custom fields are attached to lists
            data = self._request(f"/list/{lst['id']}")
            if 'custom_fields' in data:
                fields = data['custom_fields']
                for field in fields:
                    field['source_list_id'] = lst['id']
                    field['source_list_name'] = lst['name']
                all_fields.extend(fields)
                
        # Deduplicate by field ID
        unique_fields = {field['id']: field for field in all_fields}.values()
        all_fields = list(unique_fields)
        
        self.stats.custom_fields = len(all_fields)
        print(f"✅ Found {len(all_fields)} custom fields")
        return all_fields

    def get_all_dependencies(self) -> List[Dict]:
        """Extract all task dependencies and relationships"""
        print("🔗 Extracting task relationships...")
        all_relationships = []
        
        tasks = self.get_all_tasks_with_recurrence()
        
        for task in tasks:
            task_id = task['id']
            
            # Dependencies (this task blocks/is blocked by others)
            if task.get('dependencies'):
                for dep in task['dependencies']:
                    all_relationships.append({
                        'type': 'dependency',
                        'source_task_id': task_id,
                        'target_task_id': dep.get('task_id'),
                        'relationship': dep.get('type'),  # 'blocking', 'waiting_on'
                        'date_created': dep.get('date_created')
                    })
                    
            # Subtasks (parent-child relationships)
            if task.get('parent'):
                all_relationships.append({
                    'type': 'subtask',
                    'parent_task_id': task['parent'],
                    'child_task_id': task_id,
                    'relationship': 'subtask'
                })
                
        self.stats.dependencies = len(all_relationships)
        print(f"✅ Found {len(all_relationships)} task relationships")
        return all_relationships

    def extract_complete_workspace(self, save_to_file: bool = True) -> Dict[str, Any]:
        """
        Extract EVERYTHING from ClickUp workspace
        Returns complete data structure for Helios migration
        """
        print("🚀 Starting complete ClickUp workspace extraction...")
        start_time = time.time()
        
        extraction = {
            'metadata': {
                'team_id': self.team_id,
                'extraction_timestamp': int(time.time() * 1000),
                'extraction_date': datetime.now().isoformat(),
                'version': '1.0'
            },
            'spaces': self.get_all_spaces(),
            'folders': self.get_all_folders(),
            'lists': self.get_all_lists(),
            'tasks': self.get_all_tasks_with_recurrence(),
            'users': self.get_all_users(),
            'custom_fields': self.get_all_custom_fields(),
            'task_relationships': self.get_all_dependencies(),
            'statistics': {
                'spaces': self.stats.spaces,
                'folders': self.stats.folders,
                'lists': self.stats.lists, 
                'tasks': self.stats.tasks,
                'users': self.stats.users,
                'custom_fields': self.stats.custom_fields,
                'dependencies': self.stats.dependencies,
                'recurring_tasks': self.stats.recurring_tasks
            }
        }
        
        extraction_time = time.time() - start_time
        extraction['metadata']['extraction_duration_seconds'] = extraction_time
        
        if save_to_file:
            filename = f"clickup_complete_extraction_{int(time.time())}.json"
            with open(filename, 'w') as f:
                json.dump(extraction, f, indent=2, default=str)
            print(f"💾 Saved complete extraction to {filename}")
            extraction['metadata']['saved_to_file'] = filename
            
        print(f"🎉 Complete extraction finished in {extraction_time:.1f}s")
        print(f"📊 Final stats: {self.stats.tasks} tasks, {self.stats.recurring_tasks} recurring")
        
        return extraction