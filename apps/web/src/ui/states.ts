// One action for the three state primitives: a link when it has an address, else a button.
export interface StateAction {
  label: string;
  href?: string;
  onClick?: () => void;
}
