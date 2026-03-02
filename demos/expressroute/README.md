# ExpressRoute Demo

Deploys ExpressRoute-focused connectivity resources via `modules/gateways` and related networking modules.

## File

- `expressroute-demo.tfvars`

## Deploy

```bash
terraform plan  -var-file="credentials.tfvars" -var-file="demos/expressroute/expressroute-demo.tfvars"
terraform apply -var-file="credentials.tfvars" -var-file="demos/expressroute/expressroute-demo.tfvars"
```

## Notes

- Requires a valid ExpressRoute circuit/provider setup for end-to-end connectivity.
- Demo settings can optionally combine VPN/Route Server depending on selected flags.
- Main gateway implementation lives in `modules/gateways`.
# Note: Circuits may have minimum terms and early termination fees
```

## 💡 Learning Outcomes

After completing this demo, you will understand:
- ExpressRoute architecture and components
- Circuit provisioning process with service providers
- BGP configuration for ExpressRoute
- Gateway SKU selection and performance characteristics
- Cost optimization strategies for ExpressRoute
- Monitoring and troubleshooting ExpressRoute connections

## 📚 Additional Resources

- [ExpressRoute documentation](https://docs.microsoft.com/azure/expressroute/)
- [ExpressRoute partners and locations](https://docs.microsoft.com/azure/expressroute/expressroute-locations)
- [ExpressRoute pricing](https://azure.microsoft.com/pricing/details/expressroute/)
- [BGP routing optimization](https://docs.microsoft.com/azure/expressroute/expressroute-optimize-routing)

---

**⚠️ Important**: ExpressRoute circuits involve contractual commitments with service providers. Review terms, costs, and cancellation policies before provisioning production circuits.
