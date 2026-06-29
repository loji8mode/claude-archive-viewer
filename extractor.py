import json
import os
import re
import argparse
import sys

def parse_text_blocks(text_content):
    if not text_content:
        return []
        
    # 1. Normalize HTML thinking tags, if present
    possible_tags = ['antThinking', 'thinking', 'thought', 'thinking_process']
    for tag in possible_tags:
        text_content = re.sub(r'<(/?)' + tag + r'([^>]*)>', r'<\1{}\2>'.format(tag), text_content, flags=re.IGNORECASE)
    
    # 2. Pattern for system thinking text
    thought_text_pattern = r'(\[An AI assistant is thinking[^\]]*\][\s\S]*?)(?=\n\n|\Z)'
    text_content = re.sub(thought_text_pattern, r'<thinking>\1</thinking>', text_content, flags=re.IGNORECASE)

    blocks = []
    BT3 = '`' * 3
    
    pattern = re.compile(
        r'(<(?:antThinking|thinking|thought|thinking_process)[^>]*>.*?(?:</(?:antThinking|thinking|thought|thinking_process)>|$))|(' + re.escape(BT3) + r'\w*\n.*?' + re.escape(BT3) + r')', 
        re.DOTALL | re.IGNORECASE
    )
    
    last_idx = 0
    for match in pattern.finditer(text_content):
        start, end = match.span()
        
        if start > last_idx:
            pre_text = text_content[last_idx:start].strip()
            if pre_text:
                blocks.append({"type": "text", "content": pre_text})
        
        thought_block = match.group(1)
        code_block = match.group(2)
        
        if thought_block:
            content = re.sub(r'^<(?:antThinking|thinking|thought|thinking_process)[^>]*>\n?', '', thought_block, flags=re.IGNORECASE)
            content = re.sub(r'\n?</(?:antThinking|thinking|thought|thinking_process)>$', '', content, flags=re.IGNORECASE)
            
            inner_blocks = parse_text_blocks(content.strip())
            
            if len(inner_blocks) <= 1:
                blocks.append({"type": "thought", "content": content.strip()})
            else:
                for ib in inner_blocks:
                    if ib["type"] == "code":
                        blocks.append({
                            "type": "thought_code", 
                            "title": "Code in thoughts (" + ib["title"].replace("Code (", "").replace(")", "") + ")", 
                            "content": ib["content"]
                        })
                    elif ib["type"] == "text":
                        blocks.append({"type": "thought", "content": ib["content"]})
                    else:
                        blocks.append(ib)
            
        elif code_block:
            code_match = re.match(r'^' + re.escape(BT3) + r'(\w*)\n(.*?)' + re.escape(BT3) + r'$', code_block, re.DOTALL)
            if code_match:
                lang = code_match.group(1).lower().strip()
                code = code_match.group(2).strip()
                if lang in ['html', 'htm', 'svg', 'xml']:
                    style_inject = "<style>:root { --color-text-primary: white !important; --color-text-secondary: white !important; --color-text-tertiary: white !important; }</style>\n"
                    blocks.append({
                        "type": "artifact",
                        "title": "Artifact (" + lang + ")",
                        "content": style_inject + code
                    })
                else:
                    blocks.append({
                        "type": "code",
                        "title": "Code (" + (lang if lang else 'text') + ")",
                        "content": code
                    })
            else:
                blocks.append({"type": "text", "content": code_block})
                
        last_idx = end
        
    if last_idx < len(text_content):
        post_text = text_content[last_idx:].strip()
        if post_text:
            blocks.append({"type": "text", "content": post_text})
            
    if not blocks and text_content.strip():
        blocks.append({"type": "text", "content": text_content.strip()})
        
    return blocks

def build_html_viewer(json_file_path, output_html_path):
    if not os.path.exists(json_file_path):
        print("Error: File " + json_file_path + " not found!")
        return

    with open(json_file_path, 'r', encoding='utf-8') as f:
        conversations = json.load(f)

    processed_chats = []

    for conv in conversations:
        chat_data = {
            "name": conv.get("name") or "Chat (" + conv.get('uuid', '')[:5] + ")",
            "messages": []
        }
        
        for msg in conv.get('chat_messages', []):
            sender = msg.get('sender', 'unknown')
            msg_entry = {"sender": sender, "blocks": []}
            
            if 'content' in msg and msg['content']:
                for block in msg['content']:
                    b_type = block.get('type', '')
                    
                    if b_type == 'text':
                        msg_entry["blocks"].extend(parse_text_blocks(block.get("text", "")))
                    elif b_type in ['thought', 'thinking', 'redacted_thinking']:
                        t_text = block.get("thought", "") or block.get("thinking", "") or block.get("text", "")
                        if t_text:
                            msg_entry["blocks"].append({"type": "thought", "content": t_text.strip()})
                    elif b_type == 'tool_use':
                        tool_input = block.get('input', {})
                        tool_name = block.get('name', 'tool')
                        if 'widget_code' in tool_input:
                            style_inject = "<style>:root { --color-text-primary: white !important; --color-text-secondary: white !important; --color-text-tertiary: white !important; }</style>\n"
                            msg_entry["blocks"].append({
                                "type": "artifact", 
                                "title": "Interactive Widget (" + tool_name + ")", 
                                "content": style_inject + tool_input['widget_code']
                            })
                        else:
                            msg_entry["blocks"].append({
                                "type": "tool_call",
                                "title": "Tool Call: " + tool_name,
                                "content": json.dumps(tool_input, ensure_ascii=False, indent=2)
                            })
                    elif b_type == 'tool_result':
                        res_text = ""
                        for res in block.get('content', []):
                            if 'text' in res:
                                res_text += res['text'] + "\n"
                        if res_text:
                            msg_entry["blocks"].append({"type": "result", "content": res_text.strip()})
                    else:
                        for key in ['text', 'content', 'thinking', 'thought']:
                            if key in block and isinstance(block[key], str) and block[key].strip():
                                if 'think' in b_type or 'thought' in b_type or key in ['thinking', 'thought']:
                                    msg_entry["blocks"].append({"type": "thought", "content": block[key].strip()})
                                else:
                                    msg_entry["blocks"].extend(parse_text_blocks(block[key]))
                                break
            else:
                thinking = msg.get('thinking', '') or msg.get('thought', '')
                if thinking.strip():
                    msg_entry["blocks"].append({"type": "thought", "content": thinking.strip()})
                    
                text = msg.get('text', '')
                if "This block is not supported" not in text and text.strip():
                    msg_entry["blocks"].extend(parse_text_blocks(text))
            
            if msg_entry["blocks"]:
                chat_data["messages"].append(msg_entry)
                
        processed_chats.append(chat_data)

    safe_json_data = json.dumps(processed_chats, ensure_ascii=False).replace('</script>', '<\\/script>')

    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Claude Archive Smart Viewer</title>
    <style>
        :root {
            --bg: #1f1e1d;
            --bg-sidebar: #181716;
            --bg-elevated: #2b2a28;
            --bg-elevated-2: #34322f;
            --border: #3d3b38;
            --text: #ece9e4;
            --text-dim: #a8a5a0;
            --text-faint: #7d7a75;
            --accent: #cc785c;
        }
        * { box-sizing: border-box; }
        * { scrollbar-color: var(--border) var(--bg); scrollbar-width: thin; }
        ::-webkit-scrollbar { width: 10px; height: 10px; }
        ::-webkit-scrollbar-track { background: var(--bg); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 6px; }
        ::-webkit-scrollbar-thumb:hover { background: #4a4844; }

        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; display: flex; height: 100vh; background: var(--bg); color: var(--text); }
        #sidebar { width: 340px; background: var(--bg-sidebar); border-right: 1px solid var(--border); overflow-y: auto; padding: 20px 15px; display: flex; flex-direction: column; flex-shrink: 0; }
        .sidebar-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--text-faint); margin-bottom: 15px; padding-left: 10px; }
        #chat-container { flex: 1; display: flex; flex-direction: column; height: 100vh; background: var(--bg); overflow: hidden; }
        
        #chat-header { display: none; justify-content: space-between; align-items: center; padding: 15px 40px; background: var(--bg-sidebar); border-bottom: 1px solid var(--border); flex-shrink: 0; }
        #chat-title { font-weight: 600; font-size: 16px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 60%; }
        #global-toggle-btn { background: var(--bg-elevated-2); color: var(--text); border: 1px solid var(--border); padding: 8px 16px; font-size: 13px; border-radius: 6px; cursor: pointer; font-weight: 500; transition: background 0.15s; user-select: none; }
        #global-toggle-btn:hover { background: var(--border); }

        #messages { flex: 1; overflow-y: auto; padding: 40px 60px; display: flex; flex-direction: column; gap: 30px; }
        .chat-item { padding: 12px 14px; cursor: pointer; border-radius: 8px; margin-bottom: 6px; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; background: transparent; transition: background 0.2s; color: var(--text-dim); }
        .chat-item:hover { background: var(--bg-elevated); color: var(--text); }
        .chat-item.active { background: var(--bg-elevated-2); font-weight: 600; color: var(--text); }
        
        .msg-wrapper { display: flex; flex-direction: column; width: 100%; }
        .sender-name { font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-faint); margin-bottom: 8px; font-weight: bold; }
        .human .sender-name { align-self: flex-end; }
        .assistant .sender-name { align-self: flex-start; }
        .msg-body { padding: 16px 20px; border-radius: 12px; max-width: 85%; line-height: 1.6; font-size: 15.5px; white-space: pre-wrap; word-break: break-word; }
        .human .msg-body { background: var(--bg-elevated); align-self: flex-end; color: var(--text); border: 1px solid var(--border); }
        .assistant .msg-body { background: transparent; align-self: flex-start; color: var(--text); padding-left: 0; padding-right: 0; max-width: 95%; width: 100%; }
        
        .thought-block { margin: 12px 0; border: 1px dashed var(--border); border-radius: 8px; background: var(--bg-elevated); overflow: hidden; width: 100%; }
        .thought-header { padding: 10px 14px; background: var(--bg-elevated-2); cursor: pointer; display: flex; justify-content: space-between; align-items: center; font-size: 13.5px; font-weight: 600; color: var(--text-dim); user-select: none; transition: background 0.2s ease; }
        .thought-header:hover { background: var(--border); }
        
        .thought-content { padding: 14px; font-size: 14px; color: var(--text-dim); font-style: italic; white-space: pre-wrap; border-top: 1px dashed var(--border); background: var(--bg-elevated); display: none; }
        .thought-content .code-content { font-style: normal; background: #131211; color: var(--text); border-radius: 6px; margin: 0; padding: 12px; }
        .thought-content.thought-text { font-style: italic; }

        .artifact-wrapper { margin: 20px 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--bg-elevated); box-shadow: 0 2px 8px rgba(0,0,0,0.2); width: 100%; }
        .artifact-header { background: var(--bg-elevated-2); padding: 10px 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
        .artifact-title { font-size: 13.5px; font-weight: 600; color: var(--text); }
        .artifact-controls { display: flex; gap: 6px; align-items: center; }
        .art-tab-btn { background: var(--border); border: none; padding: 6px 14px; font-size: 12.5px; border-radius: 4px; cursor: pointer; color: var(--text-dim); font-weight: 500; }
        .art-tab-btn.active { background: var(--accent); color: white; }
        .art-download-btn { background: #10b981; color: white; border: none; padding: 6px 14px; font-size: 12.5px; border-radius: 4px; cursor: pointer; font-weight: 500; margin-left: 8px; }
        
        .art-preview-pane { background: var(--bg-elevated); height: 500px; width: 100%; }
        .art-iframe { width: 100%; height: 100%; border: none; background: var(--bg-elevated); }
        .art-code-pane { background: #131211; max-height: 500px; overflow-y: auto; display: none; }
        .code-content { padding: 16px; margin: 0; overflow-x: auto; font-family: monospace; font-size: 14px; color: var(--text); line-height: 1.5; text-align: left; white-space: pre; }
        
        .result-block { margin: 10px 0; padding: 12px; background: var(--bg-elevated); border-left: 4px solid var(--border); font-family: monospace; font-size: 13px; color: var(--text-dim); border-radius: 0 4px 4px 0; white-space: pre-wrap; }
        .placeholder { text-align: center; color: var(--text-faint); margin-top: 150px; font-size: 18px; }
    </style>
</head>
<body>

    <script type="application/json" id="rawChatData">
        __DATA_BUFER__
    </script>

    <div id="sidebar">
        <div class="sidebar-title">Your Claude Chats</div>
        <div id="chatList"></div>
    </div>

    <div id="chat-container">
        <div id="chat-header">
            <div id="chat-title"></div>
            <button id="global-toggle-btn" onclick="toggleAllThoughts()">👁️ Show Thoughts & Tools</button>
        </div>
        <div id="messages">
            <div class="placeholder">Select a chat from the left panel to view the history.</div>
        </div>
    </div>

    <script>
        const conversations = JSON.parse(document.getElementById('rawChatData').textContent);
        let globalThoughtsOpen = false;

        function renderChatList() {
            const list = document.getElementById('chatList');
            conversations.forEach((chat, index) => {
                const div = document.createElement('div');
                div.className = 'chat-item';
                div.innerText = chat.name;
                div.onclick = () => {
                    document.querySelectorAll('.chat-item').forEach(el => el.classList.remove('active'));
                    div.classList.add('active');
                    showChat(index);
                };
                list.appendChild(div);
            });
        }

        function toggleAllThoughts() {
            globalThoughtsOpen = !globalThoughtsOpen;
            const contents = document.querySelectorAll('.thought-content');
            const icons = document.querySelectorAll('.thought-icon');
            
            contents.forEach(content => {
                content.style.display = globalThoughtsOpen ? 'block' : 'none';
            });
            
            icons.forEach(icon => {
                icon.textContent = globalThoughtsOpen ? '▼' : '▶';
            });
            
            const btn = document.getElementById('global-toggle-btn');
            btn.textContent = globalThoughtsOpen ? '🙈 Hide Thoughts & Tools' : '👁️ Show Thoughts & Tools';
        }

        function makeCollapsible(headerText, iconEmoji) {
            const wrap = document.createElement('div');
            wrap.className = 'thought-block';

            const header = document.createElement('div');
            header.className = 'thought-header';

            const labelSpan = document.createElement('span');
            labelSpan.textContent = iconEmoji + ' ' + headerText;

            const iconSpan = document.createElement('span');
            iconSpan.className = 'thought-icon';
            iconSpan.textContent = '▶';

            header.appendChild(labelSpan);
            header.appendChild(iconSpan);

            const contentDiv = document.createElement('div');
            contentDiv.className = 'thought-content';

            header.addEventListener('click', () => {
                const isVisible = contentDiv.style.display === 'block';
                contentDiv.style.display = isVisible ? 'none' : 'block';
                iconSpan.textContent = isVisible ? '▶' : '▼';
            });

            wrap.appendChild(header);
            wrap.appendChild(contentDiv);
            return { wrap, contentDiv };
        }

        function showChat(index) {
            const header = document.getElementById('chat-header');
            const title = document.getElementById('chat-title');
            header.style.display = 'flex';
            title.textContent = conversations[index].name;
            
            globalThoughtsOpen = false;
            document.getElementById('global-toggle-btn').textContent = '👁️ Show Thoughts & Tools';

            const container = document.getElementById('messages');
            container.innerHTML = '';
            
            const messages = conversations[index].messages || [];
            if (messages.length === 0) {
                container.innerHTML = '<div class="placeholder">This chat is empty.</div>';
                return;
            }

            messages.forEach((msg, msgIdx) => {
                const wrapper = document.createElement('div');
                wrapper.className = 'msg-wrapper ' + (msg.sender === 'human' ? 'human' : 'assistant');

                const senderDiv = document.createElement('div');
                senderDiv.className = 'sender-name';
                senderDiv.textContent = msg.sender === 'human' ? 'You' : 'Claude';
                wrapper.appendChild(senderDiv);

                const bodyDiv = document.createElement('div');
                bodyDiv.className = 'msg-body';

                msg.blocks.forEach((block, blockIdx) => {
                    if (block.type === 'text') {
                        const textNode = document.createElement('div');
                        textNode.textContent = block.content;
                        textNode.style.marginBottom = "10px";
                        bodyDiv.appendChild(textNode);
                    } 
                    else if (block.type === 'thought') {
                        const { wrap, contentDiv } = makeCollapsible(
                            "Claude's Thinking Process (" + block.content.length.toLocaleString('en-US') + ' characters)',
                            '🧠'
                        );
                        contentDiv.classList.add('thought-text');
                        contentDiv.textContent = block.content;
                        bodyDiv.appendChild(wrap);
                    }
                    else if (block.type === 'tool_call') {
                        const { wrap, contentDiv } = makeCollapsible(block.title, '🔧');
                        const pre = document.createElement('pre');
                        pre.className = 'code-content';
                        const code = document.createElement('code');
                        code.textContent = block.content;
                        pre.appendChild(code);
                        contentDiv.appendChild(pre);
                        bodyDiv.appendChild(wrap);
                    }
                    else if (block.type === 'artifact') {
                        const artWrap = document.createElement('div');
                        artWrap.className = 'artifact-wrapper';
                        
                        const header = document.createElement('div');
                        header.className = 'artifact-header';
                        
                        const title = document.createElement('span');
                        title.className = 'artifact-title';
                        title.textContent = block.title;
                        header.appendChild(title);
                        
                        const controls = document.createElement('div');
                        controls.className = 'artifact-controls';
                        
                        const pBtn = document.createElement('button');
                        pBtn.className = 'art-tab-btn active';
                        pBtn.textContent = 'Preview';
                        
                        const cBtn = document.createElement('button');
                        cBtn.className = 'art-tab-btn';
                        cBtn.textContent = 'Code';
                        
                        const dlBtn = document.createElement('button');
                        dlBtn.className = 'art-download-btn';
                        dlBtn.textContent = 'Download...';
                        
                        controls.appendChild(pBtn);
                        controls.appendChild(cBtn);
                        controls.appendChild(dlBtn);
                        header.appendChild(controls);
                        artWrap.appendChild(header);
                        
                        const pPane = document.createElement('div');
                        pPane.className = 'art-preview-pane';
                        
                        const iframe = document.createElement('iframe');
                        iframe.className = 'art-iframe';
                        iframe.sandbox = 'allow-scripts allow-same-origin';
                        
                        const blob = new Blob([block.content], { type: 'text/html;charset=utf-8' });
                        iframe.src = URL.createObjectURL(blob);
                        
                        pPane.appendChild(iframe);
                        artWrap.appendChild(pPane);
                        
                        const cPane = document.createElement('div');
                        cPane.className = 'art-code-pane';
                        
                        const pre = document.createElement('pre');
                        pre.className = 'code-content';
                        const code = document.createElement('code');
                        code.textContent = block.content;
                        pre.appendChild(code);
                        cPane.appendChild(pre);
                        artWrap.appendChild(cPane);
                        
                        bodyDiv.appendChild(artWrap);
                        
                        pBtn.onclick = () => { pPane.style.display = 'block'; cPane.style.display = 'none'; pBtn.classList.add('active'); cBtn.classList.remove('active'); };
                        cBtn.onclick = () => { pPane.style.display = 'none'; cPane.style.display = 'block'; pBtn.classList.remove('active'); cBtn.classList.add('active'); };
                        dlBtn.onclick = () => {
                            const link = document.createElement('a');
                            link.href = URL.createObjectURL(blob);
                            link.download = 'file_' + msgIdx + '_' + blockIdx + '.html';
                            link.click();
                        };
                    }
                    else if (block.type === 'code') {
                        const codeWrap = document.createElement('div');
                        codeWrap.className = 'artifact-wrapper';
                        
                        const header = document.createElement('div');
                        header.className = 'artifact-header';
                        header.innerHTML = '<span class="artifact-title"></span>';
                        header.querySelector('span').textContent = block.title;
                        
                        const cPane = document.createElement('div');
                        cPane.className = 'art-code-pane';
                        cPane.style.display = 'block';
                        
                        const pre = document.createElement('pre');
                        pre.className = 'code-content';
                        const code = document.createElement('code');
                        code.textContent = block.content;
                        
                        pre.appendChild(code);
                        cPane.appendChild(pre);
                        codeWrap.appendChild(header);
                        codeWrap.appendChild(cPane);
                        bodyDiv.appendChild(codeWrap);
                    }
                    else if (block.type === 'result') {
                        const { wrap, contentDiv } = makeCollapsible(
                            'Execution Result (' + block.content.length.toLocaleString('en-US') + ' characters)',
                            '📋'
                        );
                        contentDiv.classList.add('thought-text');
                        contentDiv.textContent = '[System Execution Log]:\\n' + block.content;
                        bodyDiv.appendChild(wrap);
                    }
                });

                wrapper.appendChild(bodyDiv);
                container.appendChild(wrapper);
            });
            container.scrollTop = 0;
        }

        renderChatList();
    </script>
</body>
</html>
""".replace('__DATA_BUFER__', safe_json_data)

    with open(output_html_path, 'w', encoding='utf-8') as out:
        out.write(html_template)
        
    print("Successfully generated! File saved: " + output_html_path)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Claude Archive Smart Viewer — convert chat exports to a convenient HTML viewer.")
    parser.add_argument('-i', '--input', default='conversations.json', help="Path to the input JSON file")
    parser.add_argument('-o', '--output', default='viewer.html', help="Path to the output HTML file")
    
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found.")
        sys.exit(1)

    try:
        build_html_viewer(args.input, args.output)
    except json.JSONDecodeError:
        print(f"Error: File '{args.input}' contains invalid JSON.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)