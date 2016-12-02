# Setup

### Install required Python modules

```shell
pip install -r requirements.txt
```

### Set AWS credentials in environment

```shell
export AWS_ACCESS_KEY_ID=XXX
export AWS_SECRET_ACCESS_KEY=XXX
```

### Update configuration

Edit vars/local.yml to define your setup.

# Launch cluster
```shell
./launch_cluser.sh
```

# Provision cluster
```shell
./provision_cluster.sh
```

# Terminate cluster
```shell
./terminate_cluster.sh
```
