import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { INSTRUCTION_MAX_LENGTH, QUICK_INSTRUCTIONS } from './instructions';
import styles from './ReviseComposer.module.css';

export interface ReviseComposerProps {
  /** 请求中：禁用输入并显示「正在调整…」 */
  revising: boolean;
  onSubmit: (instruction: string) => void;
}

/**
 * 改计划对话条：计划生成后固定在底部。
 * 移动端停在底部 Tab 之上，页面内容靠 PlanPage 的 padding 让位；
 * body 上打标记，让 Toast 抬到输入框上方，避免盖住发送按钮。
 */
export function ReviseComposer({ revising, onSubmit }: ReviseComposerProps) {
  const [text, setText] = useState('');

  useEffect(() => {
    document.body.dataset.composer = 'on';
    return () => {
      delete document.body.dataset.composer;
    };
  }, []);

  const submit = (instruction: string): void => {
    const trimmed = instruction.trim();
    if (!trimmed || revising) return;
    onSubmit(trimmed);
    setText('');
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    submit(text);
  };

  return (
    <div className={styles.bar} role="group" aria-label="改计划">
      <div className={styles.inner}>
        <ul className={styles.chips}>
          {QUICK_INSTRUCTIONS.map((instruction) => (
            <li key={instruction}>
              <Chip
                label={instruction}
                selected={false}
                showMark={false}
                disabled={revising}
                onToggle={() => submit(instruction)}
              />
            </li>
          ))}
        </ul>

        <form className={styles.form} onSubmit={handleSubmit}>
          <input
            className={styles.input}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={revising ? '正在调整…' : '告诉 AI 怎么改，例如：第二天想吃清淡点，别放鸡蛋'}
            aria-label="告诉 AI 怎么改这份计划"
            maxLength={INSTRUCTION_MAX_LENGTH}
            disabled={revising}
          />
          <Button type="submit" loading={revising} disabled={revising || text.trim().length === 0}>
            {revising ? '正在调整…' : '发送'}
          </Button>
        </form>

        <p className={styles.hint} role="status">
          {revising
            ? '正在调整…未涉及的餐次保持不变'
            : '只改你提到的那几餐；改完会逐条列出改动，没改成功会给出原因'}
        </p>
      </div>
    </div>
  );
}
