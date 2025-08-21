import { useEffect, useState } from 'react';

export function useClickUpTasks() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  const CLICKUP_API_KEY = import.meta.env.VITE_CLICKUP_API_KEY;
  const LIST_ID = import.meta.env.VITE_CLICKUP_LIST_ID; // Set this in your .env

  useEffect(() => {
    async function fetchTasks() {
      try {
        const response = await fetch(`https://api.clickup.com/api/v2/list/${LIST_ID}/task`, {
          headers: {
            Authorization: CLICKUP_API_KEY
          }
        });

        const data = await response.json();
        setTasks(data.tasks || []);
      } catch (err) {
        console.error('Error fetching ClickUp tasks:', err);
      } finally {
        setLoading(false);
      }
    }

    fetchTasks();
  }, [CLICKUP_API_KEY, LIST_ID]);

  return { tasks, loading };
}
