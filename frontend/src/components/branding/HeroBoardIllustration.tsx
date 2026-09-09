import { useId } from "react";
import { LogoGlyphs } from "./Logo";

/** Newly drawn vector assembly: layered PCB, plated contacts and extruded housings. */
export function HeroBoardIllustration() {
  const id = useId().replace(/:/g, "");
  return <svg className="hero-board-art" viewBox="0 0 640 350" focusable="false" aria-hidden="true">
    <defs>
      <linearGradient id={`${id}-pcb`} x2="0.8" y2="1"><stop stopColor="#185b3c" /><stop offset="0.55" stopColor="#0e3829" /><stop offset="1" stopColor="#071f18" /></linearGradient>
      <linearGradient id={`${id}-metal`} x2="0.9" y2="1"><stop stopColor="#e0e7da" /><stop offset="0.45" stopColor="#8caa98" /><stop offset="0.5" stopColor="#c2cdbd" /><stop offset="1" stopColor="#526c5c" /></linearGradient>
      <linearGradient id={`${id}-case`} x2="0.2" y2="1"><stop stopColor="#34483e" /><stop offset="1" stopColor="#07110d" /></linearGradient>
      <pattern id={`${id}-grid`} width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="currentColor" strokeOpacity=".12" strokeWidth=".5" /></pattern>
    </defs>
    <rect x="30" y="15" width="580" height="320" fill={`url(#${id}-grid)`} />
    <g className="hero-board-art__drawing" transform="translate(116 61) rotate(9 190 115) skewX(-10)">
      <path d="M15 13H340L365 34V208L349 230H15Z" fill="#030f0a" stroke="#59765d" strokeWidth="2" />
      <path d="M15 5H340L365 26V200L349 222H15Z" fill={`url(#${id}-pcb)`} stroke="#528764" strokeWidth="2" />
      <path d="M24 13H335L356 31V196L344 213H24Z" fill="none" stroke="#32b669" strokeOpacity=".35" />
      <g className="hardware-board__traces" strokeWidth="1">
        <path d="M45 66H116L138 88H220L247 61H322M48 89H110L131 111H184M78 178H123L143 156H288L317 184H341M115 34V58H154L176 80V100M158 37V64H208V101M253 35V75L283 101V130M326 42V95L303 117V156M91 115V150L115 174V203M159 203V177H221M199 203V187H281M55 138H74V163H103M285 192V178H331V130" />
        <path d="M50 100H93L114 121V137H159M207 113V87H242L272 56M244 154V173H265L277 185M137 129V114L124 101V85" />
        {[78, 108, 140, 182, 248, 286, 329].map((x, i) => <circle key={x} cx={x} cy={73 + (i % 3) * 38} r="2.5" fill="#a3bb6a" stroke="#234f35" />)}
      </g>
      <g fill="#a8b780" stroke="#293d29" strokeWidth="2">{[[29, 23], [342, 35], [30, 207], [340, 203]].map(([x,y], i) => <g key={i}><circle cx={x} cy={y} r="7" /><circle cx={x} cy={y} r="3.5" fill="#071a12" stroke="none" /></g>)}</g>
      {/* Raised female pin headers: top face, front wall, individual sockets. */}
      {[{x:97,y:20,n:14},{x:124,y:199,n:8},{x:253,y:199,n:6}].map(({x,y,n}) => <g key={x}>
        <path d={`M${String(x)} ${String(y)}h${String(n*14)}v15l-5 6h-${String(n*14)}v-15Z`} fill="#07100c" stroke="#476956" />
        <rect x={x} y={y} width={n*14} height="13" fill="#233c30" stroke="#688171" />
        {Array.from({length:n},(_,i)=><g key={i}><rect x={x+i*14+3} y={y+3} width="8" height="7" fill="#010705" stroke="#8ca18a" strokeWidth=".7" /><path d={`M${String(x+i*14+4)} ${String(y+21)}v4`} stroke="#b5ad73" strokeWidth="2" /></g>)}
      </g>)}
      {/* USB Type B shell and the recessed connector face. */}
      <g><path d="M0 53L17 40H78V91L61 107H0Z" fill="#597064" stroke="#b7c7b4" /><path d="M0 53H61L78 40H17Z" fill="#d5dfcc" /><path d="M61 53L78 40V91L61 107Z" fill="#7e9282" /><rect x="0" y="53" width="61" height="54" rx="3" fill={`url(#${id}-metal)`} stroke="#dce2d1" /><path d="M10 64H48L54 71V95H8V71Z" fill="#0a1c15" stroke="#526759" strokeWidth="3" /><path d="M19 73H42V90H19Z" fill="#a3b4a2" /><path d="M23 76V85M36 76V85" stroke="#243e2c" strokeWidth="3" /></g>
      {/* DC jack body with the circular barrel opening. */}
      <g><path d="M12 156L27 140H77V178L62 196H12Z" fill="#07120d" stroke="#466350" /><path d="M12 156H62L77 140H27Z" fill="#304a3c" /><rect x="12" y="156" width="50" height="40" rx="4" fill={`url(#${id}-case)`} /><ellipse cx="35" cy="176" rx="16" ry="13" fill="#000805" stroke="#537361" strokeWidth="3" /><circle cx="35" cy="176" r="4" fill="#a1b39d" /></g>
      {/* Through-hole MCU with 28 plated leads and a moulded orientation notch. */}
      <g>{Array.from({length:14},(_,i)=><g key={i}><rect x={140+i*11} y="121" width="5" height="13" rx="1" fill={`url(#${id}-metal)`} /><rect x={140+i*11} y="164" width="5" height="14" rx="1" fill={`url(#${id}-metal)`} /></g>)}
        <path d="M133 135L139 128H296V161L290 170H133Z" fill="#050c08" stroke="#42604b" /><rect x="133" y="128" width="157" height="35" rx="3" fill={`url(#${id}-case)`} stroke="#657362" /><path d="M133 139a6 6 0 0 1 0 12" fill="#060c09" stroke="#617161" /><text x="158" y="149" fill="#b4c4b1" fontSize="9" fontFamily="monospace">ATmega328P / MCU</text>
      </g>
      {/* USB interface IC, resonator, regulator and passive components. */}
      <g><rect x="93" y="69" width="31" height="31" fill="#101c15" stroke="#a1ad8e" />
        {Array.from({length:6},(_,i)=><path key={i} d={`M89 ${String(72+i*5)}h5M124 ${String(72+i*5)}h5`} stroke="#c0bd95" strokeWidth="2" />)}
        <rect x="87" y="110" width="33" height="15" rx="7" fill={`url(#${id}-metal)`} stroke="#c5d3bd" /><path d="M94 117H111" stroke="#667b66" />
        <rect x="70" y="140" width="17" height="19" fill="#15251a" stroke="#809579" /><path d="M73 159V165M78 159V165M83 159V165" stroke="#bac3a1" strokeWidth="2" />
        {[98,116].map(x=><g key={x}><rect x={x} y="165" width="13" height="15" rx="3" fill="#556c56" /><ellipse cx={x+6.5} cy="165" rx="6.5" ry="4" fill="#c1ceb1" /><path d={`M${String(x+3)} 165h7`} stroke="#52644e" /></g>)}
        {[[151,87],[174,87],[316,119],[316,139],[68,115],[274,84]].map(([x,y],i)=><g key={i}><rect x={x} y={y} width="12" height="6" fill="#a9bba0" /><rect x={(x ?? 0)+3} y={y} width="6" height="6" fill="#6e7650" /></g>)}
      </g>
      <g transform="translate(210 57) scale(.42)" color="#d1e6ca"><LogoGlyphs /></g>
      <g fill="#abc9a8" fontSize="7" fontFamily="monospace"><text x="151" y="49">DIGITAL / GPIO</text><text x="256" y="191">ANALOG IN</text><text x="151" y="191">POWER</text><text x="78" y="57">USB</text><text x="290" y="92">UNO</text></g>
      <rect x="321" y="74" width="7" height="4" fill="#00ff66" /><circle cx="324" cy="76" r="8" fill="#00ff66" opacity=".12" />
    </g>
    <g className="hero-board-art__annotations" fill="none" stroke="currentColor" strokeWidth=".8">
      <path d="M90 97V68H124M477 97V68H447M90 244V276H124M477 244V276H447" />
      <path d="M157 110L104 73H40M416 113L478 43H584M378 234L476 286H583" />
      <circle cx="157" cy="110" r="3" /><circle cx="416" cy="113" r="3" /><circle cx="378" cy="234" r="3" />
      <path d="M165 32H426M165 28V36M426 28V36" opacity=".4" />
    </g>
    <g className="hero-board-art__labels" fill="currentColor" fontFamily="monospace" fontSize="11"><text x="40" y="65">USB TYPE-B</text><text x="485" y="35">DIGITAL I/O</text><text x="483" y="303">MCU / DIP-28</text><text x="40" y="322" fontSize="9" letterSpacing="2">ACKB · CONTROLLER STUDY</text></g>
  </svg>;
}
