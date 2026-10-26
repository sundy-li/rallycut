import { useEffect } from "react";
import { Keyboard, X } from "lucide-react";
import { SHORTCUT_GROUPS } from "../lib/shortcuts";

interface Props {
  onClose: () => void;
}

/** Read-only list of every shortcut, grouped like CapCut's shortcut panel. */
export default function ShortcutsPanel({ onClose }: Props) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section
        className="shortcuts-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h2 id="shortcuts-title">
            <Keyboard size={16} />
            快捷键
          </h2>
          <button
            className="icon-button"
            aria-label="关闭快捷键"
            title="关闭（Esc）"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <div className="shortcuts-grid">
          {SHORTCUT_GROUPS.map((group) => (
            <section key={group.title} className="shortcut-group">
              <h3>
                {group.title}
                {group.note && <span>{group.note}</span>}
              </h3>
              <dl>
                {group.rows.map((row) => (
                  <div
                    key={row.label + row.keys.join()}
                    className="shortcut-row"
                  >
                    <dt>{row.label}</dt>
                    <dd>
                      {row.keys.map((k, i) => (
                        <span key={k}>
                          {i > 0 && <i>/</i>}
                          <kbd>{k}</kbd>
                        </span>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
        <p className="shortcuts-foot">
          正在输入文字时单键快捷键不生效；弹窗打开时编辑快捷键暂停。
        </p>
      </section>
    </div>
  );
}
