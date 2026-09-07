import json
import pandas as pd
from datetime import datetime
import os

def analyze_and_store_followups(filepath, output_dir="artifacts/analytics"):
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    with open(filepath, 'r') as f:
        data = json.load(f)

    records = []
    for email_group in data.get('emails', []):
        messages = email_group.get('messages', [])
        messages.sort(key=lambda x: datetime.fromisoformat(x['date_sent'].replace('Z', '+00:00')))
        
        for i in range(len(messages)):
            msg = messages[i]
            time_since_last_msg_mins = None
            if i > 0:
                prev_date = datetime.fromisoformat(messages[i-1]['date_sent'].replace('Z', '+00:00'))
                time_since_last_msg_mins = ((datetime.fromisoformat(msg['date_sent'].replace('Z', '+00:00'))) - prev_date).total_seconds() / 60.0
                
            records.append({
                'thread_id': msg.get('thread_id'),
                'sent_from': msg.get('sent_from'),
                'date_sent': msg['date_sent'],
                'is_followup': i > 0,
                'time_since_last_msg_mins': time_since_last_msg_mins
            })

    df = pd.DataFrame(records)
    followups = df[df['is_followup'] == True].copy()
    
    # Export 1: Raw Follow-up Data (for visualization/dashboards)
    raw_csv_path = os.path.join(output_dir, "raw_followup_data.csv")
    followups.to_csv(raw_csv_path, index=False)
    
    # Export 2: Summary Stats by Sender (JSON for dynamic LLM configurations)
    sender_stats = followups.groupby('sent_from')['time_since_last_msg_mins'].agg(['mean', 'median', 'count']).sort_values(by='mean')
    stats_json_path = os.path.join(output_dir, "sender_followup_stats.json")
    sender_stats.to_json(stats_json_path, orient="index")
    
    print(f"Analytics successfully exported to {output_dir}")

if __name__ == "__main__":
    analyze_and_store_followups("emails_candidate.json")