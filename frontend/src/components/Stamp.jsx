// Brand mark — "The Vine" (Direction B): bordeaux circle, cream berry cluster.
// Full 7-berry bunch at nav scale; simplified 3-berry triangle below 30px.
export default function Stamp({ size = 32 }) {
  const small = size < 30;
  const inner = Math.round(size * 0.61);
  return (
    <div
      aria-hidden="true"
      style={{
        width: size, height: size, borderRadius: '50%', background: 'var(--bordeaux)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none',
      }}
    >
      {small ? (
        <svg width={inner} height={inner} viewBox="10 24 42 42" fill="none">
          <circle cx="22" cy="31" r="8" fill="#F5EFE6" opacity="0.82" />
          <circle cx="37" cy="31" r="8" fill="#F5EFE6" opacity="0.82" />
          <circle cx="29" cy="44" r="8" fill="#F5EFE6" opacity="0.82" />
        </svg>
      ) : (
        <svg width={inner} height={inner} viewBox="2 18 58 52" fill="none">
          <circle cx="22" cy="31" r="7" fill="#F5EFE6" opacity="0.75" />
          <circle cx="37" cy="31" r="7" fill="#F5EFE6" opacity="0.75" />
          <circle cx="14" cy="44" r="7" fill="#F5EFE6" opacity="0.75" />
          <circle cx="29" cy="44" r="7" fill="#F5EFE6" opacity="0.75" />
          <circle cx="44" cy="44" r="7" fill="#F5EFE6" opacity="0.75" />
          <circle cx="22" cy="57" r="7" fill="#F5EFE6" opacity="0.75" />
          <circle cx="37" cy="57" r="7" fill="#F5EFE6" opacity="0.75" />
        </svg>
      )}
    </div>
  );
}
