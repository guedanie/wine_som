export default function Btn({ children, variant, onClick, style, disabled }) {
  const cls = 't-btn' + (variant === 'ghost' ? ' t-btn--ghost' : '');
  return (
    <button className={cls} style={style} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}
