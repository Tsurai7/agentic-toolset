package sample

// Compute calls Add and Mul, so a structural graph has real call edges to find.
func Compute(x, y int) int {
	s := Add(x, y)
	p := Mul(x, y)
	return Add(s, p)
}

// Total chains another call onto Compute.
func Total(items []int) int {
	acc := 0
	for _, it := range items {
		acc = Add(acc, Compute(it, it))
	}
	return acc
}
