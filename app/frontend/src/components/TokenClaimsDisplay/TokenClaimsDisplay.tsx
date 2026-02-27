import { useMsal } from "@azure/msal-react";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getTokenClaims } from "../../authConfig";
import { useState, useEffect } from "react";

type Claim = {
    name: string;
    value: string;
};

export const TokenClaimsDisplay = () => {
    const { instance } = useMsal();
    const activeAccount = instance.getActiveAccount();
    const [claims, setClaims] = useState<Record<string, unknown> | undefined>(undefined);

    useEffect(() => {
        const fetchClaims = async () => {
            setClaims(await getTokenClaims(instance));
        };

        fetchClaims();
    }, []);

    const ToString = (a: string | any) => {
        if (typeof a === "string") {
            return a;
        } else {
            return JSON.stringify(a);
        }
    };

    let createClaims = (o: Record<string, unknown> | undefined) => {
        return Object.keys(o ?? {}).map((key: string) => {
            let originalKey = key;
            try {
                const url = new URL(key);
                const parts = url.pathname.split("/");
                key = parts[parts.length - 1];
            } catch (error) {
                // Do not parse key if it's not a URL
            }
            return { name: key, value: ToString((o ?? {})[originalKey]) };
        });
    };
    const items: Claim[] = createClaims(claims);

    return (
        <div className="mt-5">
            <Label>ID Token Claims</Label>
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Value</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {items.map(item => (
                        <TableRow key={item.name}>
                            <TableCell>{item.name}</TableCell>
                            <TableCell>{item.value}</TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </div>
    );
};
